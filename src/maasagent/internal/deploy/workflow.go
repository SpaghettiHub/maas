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
	"errors"
	"fmt"
	"net/netip"
	"time"

	tworkflow "go.temporal.io/sdk/workflow"

	"maas.io/core/src/maasagent/internal/power"
	"maas.io/core/src/maasagent/internal/workflow"
)

const (
	NodeStatusNew = iota
	NodeStatusCommissioning
	NodeStatusFailedCommissioning
	NodeStatusMissing
	NodeStatusReady
	NodeStatusReserved
	NodeStatusDeployed
	NodeStatusRetired
	NodeStatusBroken
	NodeStatusDeploying
	NodeStatusAllocated
	NodeStatusFailedDeployment
	NodeStatusReleasing
	NodeStatusFailedReleasing
	NodeStatusRescueMode
	NodeStatusEnteringRescueMode
	NodeStatusFailedEnteringRescueMode
	NodeStatusExitingRescueMode
	NodeStatusFailedExitingRescueMode
	NodeStatusTesting
	NodeStatusFailedTesting
)

var (
	ErrInvalidNodeStatus           = errors.New("the given node is in the incorrect status for this operation")
	ErrIPAllocationConflict        = errors.New("one or more IPs proposed for allocation were already allocated")
	ErrInsufficientUserPermissions = errors.New("requesting user does not have permissions for this operation")
	ErrInvalidStorageConfig        = errors.New("the storage configuration is invalid with the given params")
)

type AllocateIPsInput struct {
	SystemID string `json:"system_id"`
}

type ProposeIPInput struct {
	SystemID string `json:"system_id"`
}

type ProposeIPResult struct {
	SystemID string        `json:"system_id"`
	IPs      []*netip.Addr `json:"ips"`
	MACs     []string      `json:"macs"`
}

type ClaimIPsInput struct {
	SystemID string        `json:"system_id"`
	IPs      []*netip.Addr `json:"ips"`
	MACs     []string      `json:"macs"`
}

type DeployInput struct {
	SystemID         string `json:"system_id"`
	Queue            string `json:"queue"`
	Osystem          string `json:"osystem"`
	DistroSeries     string `json:"distro_series"`
	HWEKernel        string `json:"hwe_kernel"`
	UserData         string `json:"user_data"`
	RequestingUserID int64  `json:"requesting_user_id"`
	InstallKVM       bool   `json:"install_kvm"`
	RegisterVMHost   bool   `json:"install_vmhost"`
	EnableHWSync     bool   `json:"enable_hw_sync"`
	EphemeralDeploy  bool   `json:"ephemeral_deploy"`
}

type GetPowerParamsInput struct {
	SystemID string `json:"system_id"`
}

type GetPowerParamsResult struct {
	PowerParams map[string]interface{} `json:"power_params"`
	PowerType   string                 `json:"power_type"`
}

type SetDeployParamsResult struct {
	BiosBootMethod  string `json:"bios_boot_method"`
	Osystem         string `json:"osystem"`
	DistroSeries    string `json:"distro_series"`
	Architecture    string `json:"architecture"`
	MinHWEKernel    string `json:"min_hwe_kernel"`
	HWEKernel       string `json:"hwe_kernel"`
	PowerState      string `json:"power_state"`
	Status          int    `json:"status"`
	PreviousStatus  int    `json:"previous_status"`
	EphemeralDeploy bool   `json:"ephemeral_deploy"`
	RegisterKVMHost bool   `json:"register_kvm_host"`
	InstallKVM      bool   `json:"install_kvm"`
	InstallRackd    bool   `json:"install_rackd"`
	Netboot         bool   `json:"netboot"`
	Dynamic         bool   `json:"dynamic"`
	EnableHWSync    bool   `json:"enable_hw_sync"`
}

type DeployEphemeralOSInput struct {
	SystemID     string                `json:"system_id"`
	PowerParams  GetPowerParamsResult  `json:"power_params"`
	DeployParams SetDeployParamsResult `json:"deploy_params"`
}

type DeployInstalledOSInput struct {
	SystemID     string                `json:"system_id"`
	PowerParams  GetPowerParamsResult  `json:"power_params"`
	DeployParams SetDeployParamsResult `json:"deploy_params"`
}

type GetUserInfoInput struct {
	UserID int64 `json:"user_id"`
}

type GetUserInfoResult struct {
	IsSuperuser bool `json:"is_superuser"`
}

type CheckDiskStatusInput struct {
	SystemID string `json:"system_id"`
}

type CheckDiskStatusResult struct {
	Diskless bool `json:"diskless"`
}

type SetBootOrderInput struct {
	SystemID string `json:"system_id"`
	Netboot  bool   `json:"netboot"`
}

type NodeStatusInput struct {
	SystemID string `json:"system_id"`
	Status   int    `json:"status"`
}

func checkForBootInterfaceLease(ctx tworkflow.Context, systemID string) error {
	var (
		leaseSig *workflow.LeaseSignal
		err      error
	)

	for leaseSig == nil || !leaseSig.IsBootInterface {
		leaseSig, err = workflow.HandleSignal[workflow.LeaseSignal](ctx, fmt.Sprintf("leases:%s", systemID))
		if err != nil {
			return err
		}
	}

	return nil
}

func checkAllBootAssets(ctx tworkflow.Context, systemID string, bootAssets []string) error {
checkLoop:
	for {
		bootAssetSig, err := workflow.HandleSignal[workflow.BootAssetSignal](ctx, fmt.Sprintf("boot-assets:%s", systemID))
		if err != nil {
			return err
		}

		for i, bootasset := range bootAssets {
			if bootAssetSig.BootAsset == bootasset {
				if i < len(bootAssets)-1 {
					bootAssets = append(bootAssets[:i], bootAssets[i+1:]...)
				} else {
					bootAssets = bootAssets[:i]
				}
			}
		}

		if len(bootAssets) == 0 {
			break checkLoop
		}
	}

	return nil
}

func AllocateIPs(ctx tworkflow.Context, input AllocateIPsInput) error {
	var (
		proposedIPs   ProposeIPResult
		checkIPInput  workflow.CheckIPParam
		checkIPResult workflow.CheckIPResult
	)

	err := tworkflow.ExecuteActivity(
		ctx,
		"propose-ip",
		ProposeIPInput(input),
	).Get(ctx, &proposedIPs)
	if err != nil {
		return err
	}

	checkIPInput.IPs = make([]*netip.Addr, len(proposedIPs.IPs))
	copy(checkIPInput.IPs, proposedIPs.IPs)

	err = tworkflow.ExecuteChildWorkflow(ctx, workflow.CheckIP, checkIPInput).Get(ctx, &checkIPResult)
	if err != nil {
		return err
	}

	var claimIPs ClaimIPsInput
	claimIPs.MACs = make([]string, len(proposedIPs.MACs))
	copy(claimIPs.MACs, proposedIPs.MACs)

	for _, ip := range checkIPInput.IPs {
		if _, ok := checkIPResult.IPs[ip]; !ok {
			claimIPs.IPs = append(claimIPs.IPs, ip)
		} else {
			claimIPs.IPs = append(claimIPs.IPs, nil)
		}
	}

	err = tworkflow.ExecuteActivity(ctx, "claim-ips", claimIPs).Get(ctx, nil)
	if err != nil {
		return err
	}

	return nil
}

func DeployEphemeralOS(ctx tworkflow.Context, input DeployEphemeralOSInput) error {
	var err error

	if input.PowerParams.PowerType != "manual" {
		var (
			powerActivity string
			powerInput    any
		)

		if input.DeployParams.PowerState == "on" {
			powerActivity = "power-cycle"
			powerInput = power.PowerCycleParam{
				DriverOpts: input.PowerParams.PowerParams,
				DriverType: input.PowerParams.PowerType,
			}
		} else {
			powerActivity = "power-on"
			powerInput = power.PowerOnParam{
				DriverOpts: input.PowerParams.PowerParams,
				DriverType: input.PowerParams.PowerType,
			}
		}

		err = tworkflow.ExecuteActivity(ctx, powerActivity, powerInput).Get(ctx, nil)
		if err != nil {
			return err
		}
	}

	// TODO update power state

	err = checkForBootInterfaceLease(ctx, input.SystemID)
	if err != nil {
		return err
	}

	err = checkAllBootAssets(ctx, input.SystemID, []string{
		fmt.Sprintf("%s/%s", input.DeployParams.Osystem, input.DeployParams.DistroSeries),
		input.DeployParams.HWEKernel,
	})
	if err != nil {
		return err
	}

	_, err = workflow.HandleSignal[workflow.CurtinDownloadSignal](ctx, fmt.Sprintf("curtin-download:%s", input.SystemID))
	if err != nil {
		return err
	}

	_, err = workflow.HandleSignal[workflow.CurtinFinishedSignal](ctx, fmt.Sprintf("curtin-finished:%s", input.SystemID))
	if err != nil {
		return err
	}

	return nil
}

func DeployInstalledOS(ctx tworkflow.Context, input DeployInstalledOSInput) error {
	var err error

	if input.PowerParams.PowerType != "manual" {
		err = tworkflow.ExecuteActivity(ctx, "power-cycle", power.PowerCycleParam{
			DriverOpts: input.PowerParams.PowerParams,
			DriverType: input.PowerParams.PowerType,
		}).Get(ctx, nil)
		if err != nil {
			return err
		}
	}

	// TODO update power state

	err = checkForBootInterfaceLease(ctx, input.SystemID)
	if err != nil {
		return err
	}

	err = checkAllBootAssets(ctx, input.SystemID, []string{})
	if err != nil {
		return err
	}

	_, err = workflow.HandleSignal[workflow.CloudInitDownloaded](ctx, fmt.Sprintf("cloud-init-download:%s", input.SystemID))
	if err != nil {
		return err
	}

	_, err = workflow.HandleSignal[workflow.CloudInitFinished](ctx, fmt.Sprintf("cloud-init-finished:%s", input.SystemID))
	if err != nil {
		return err
	}

	return nil
}

func failDeployment(systemID string, err error, additionalInfo ...string) error {
	err = fmt.Errorf("failed deployment for %s: %w", systemID, err)

	for _, a := range additionalInfo {
		err = fmt.Errorf("%w, %s", err, a)
	}

	return err
}

func Deploy(ctx tworkflow.Context, input DeployInput) error {
	getPowerParamsCtx := tworkflow.WithActivityOptions(ctx, tworkflow.ActivityOptions{
		StartToCloseTimeout: 10 * time.Second,
	})

	var powerParams GetPowerParamsResult

	// just return the futurue, we'll fetch the result after both
	// power and deploy parameter activities are executed
	powerParamsFuture := tworkflow.ExecuteActivity(
		getPowerParamsCtx,
		"get-power-params",
		GetPowerParamsInput{
			SystemID: input.SystemID,
		},
	)

	getUserInfoCtx := tworkflow.WithActivityOptions(ctx, tworkflow.ActivityOptions{
		StartToCloseTimeout: 10 * time.Second,
	})

	var userInfo GetUserInfoResult

	userInfoFuture := tworkflow.ExecuteActivity(
		getUserInfoCtx,
		"get-user-info",
		GetUserInfoInput{
			UserID: input.RequestingUserID,
		},
	)

	err := powerParamsFuture.Get(getPowerParamsCtx, &powerParams)
	if err != nil {
		return err
	}

	err = userInfoFuture.Get(getUserInfoCtx, &userInfo)
	if err != nil {
		return err
	}

	if (input.InstallKVM || input.RegisterVMHost) && !userInfo.IsSuperuser {
		return failDeployment(
			input.SystemID,
			ErrInsufficientUserPermissions,
			"you must be a MAAS administrator to deploy a machine as a MAAS-managed VM host",
		)
	}

	if !input.EphemeralDeploy {
		var diskStatus CheckDiskStatusResult

		checkDiskStatusCtx := tworkflow.WithActivityOptions(ctx, tworkflow.ActivityOptions{
			StartToCloseTimeout: 10 * time.Second,
		})

		err = tworkflow.ExecuteActivity(checkDiskStatusCtx, "check-disk-status", CheckDiskStatusInput{
			SystemID: input.SystemID,
		}).Get(checkDiskStatusCtx, &diskStatus)
		if err != nil {
			return err
		}

		if diskStatus.Diskless {
			return failDeployment(
				input.SystemID,
				ErrInvalidStorageConfig,
				"cannot deploy to a disk in a diskless machine. Deploy to memory must be used instead.",
			)
		}
	}

	var deployParams SetDeployParamsResult

	setDeployParamsCtx := tworkflow.WithActivityOptions(ctx, tworkflow.ActivityOptions{
		StartToCloseTimeout: 10 * time.Second,
	})

	err = tworkflow.ExecuteActivity(
		setDeployParamsCtx,
		"set-deploy-params",
		input,
	).Get(setDeployParamsCtx, &deployParams)
	if err != nil {
		return err
	}

	if deployParams.Status != NodeStatusReady && deployParams.Status != NodeStatusAllocated {
		return failDeployment(input.SystemID, ErrInvalidNodeStatus)
	}

	err = tworkflow.ExecuteChildWorkflow(ctx, AllocateIPs, AllocateIPsInput{
		SystemID: input.SystemID,
	}).Get(ctx, nil)
	if err != nil {
		return err
	}

	err = tworkflow.ExecuteChildWorkflow(ctx, DeployEphemeralOS, DeployEphemeralOSInput{
		SystemID:     input.SystemID,
		PowerParams:  powerParams,
		DeployParams: deployParams,
	}).Get(ctx, nil)
	if err != nil {
		return err
	}

	if !input.EphemeralDeploy {
		err = tworkflow.ExecuteActivity(
			ctx,
			"set-boot-order",
			SetBootOrderInput{SystemID: input.SystemID, Netboot: false},
		).Get(ctx, nil)
		if err != nil {
			return err
		}

		err = tworkflow.ExecuteChildWorkflow(ctx, DeployInstalledOS, DeployInstalledOSInput{
			SystemID:     input.SystemID,
			PowerParams:  powerParams,
			DeployParams: deployParams,
		}).Get(ctx, nil)
		if err != nil {
			return err
		}
	}

	return tworkflow.ExecuteActivity(ctx, "update-node-status", NodeStatusInput{Status: NodeStatusDeployed}).Get(ctx, nil)
}
