// Copyright (c) 2024 Canonical Ltd
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.
package deploy

import (
	"fmt"
	"time"

	tworker "go.temporal.io/sdk/worker"
	tworkflow "go.temporal.io/sdk/workflow"

	"maas.io/core/src/maasagent/internal/workflow"
	"maas.io/core/src/maasagent/internal/workflow/worker"
)

const deployServiceWorkerPoolGroup = "deploy-service"

type DeployService struct {
	pool     *worker.WorkerPool
	systemID string
}

func NewDeployService(systemID string, pool *worker.WorkerPool) *DeployService {
	return &DeployService{
		systemID: systemID,
		pool:     pool,
	}
}

func (s *DeployService) ConfiguratorName() string {
	return "configure-deploy-service"
}

func (s *DeployService) Configure(ctx tworkflow.Context, systemID string) error {
	s.pool.RemoveWorkers(deployServiceWorkerPoolGroup)

	type getAgentVLANsParam struct {
		SystemID string `json:"system_id"`
	}

	type getAgentVLANsResult struct {
		VLANs []int `json:"vlans"`
	}

	param := getAgentVLANsParam{SystemID: systemID}

	var vlansResult getAgentVLANsResult
	err := tworkflow.ExecuteActivity(
		tworkflow.WithActivityOptions(ctx,
			tworkflow.ActivityOptions{
				TaskQueue:              "region",
				ScheduleToCloseTimeout: 60 * time.Second,
			}),
		"get-rack-controller-vlans", param).
		Get(ctx, &vlansResult)

	if err != nil {
		return err
	}

	activities := map[string]interface{}{}

	workflows := map[string]interface{}{
		"allocate-ip":         AllocateIPs,
		"check-ip":            workflow.CheckIP,
		"deploy":              Deploy,
		"deploy-ephemeral-os": DeployEphemeralOS,
		"deploy-installed-os": DeployInstalledOS,
	}

	// Register workers listening VLAN specific task queue and a common one
	// for fallback scenario for routable access.
	for _, vlan := range vlansResult.VLANs {
		taskQueue := fmt.Sprintf("agent:deploy@vlan-%d", vlan)
		if err := s.pool.AddWorker(deployServiceWorkerPoolGroup, taskQueue,
			workflows, activities, tworker.Options{}); err != nil {
			s.pool.RemoveWorkers(deployServiceWorkerPoolGroup)
			return err
		}
	}

	return nil
}
