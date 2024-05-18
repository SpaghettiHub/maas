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
package workflow

import (
	"errors"

	"go.temporal.io/sdk/workflow"
)

var (
	ErrSignalClosed = errors.New("requested signal closed")
)

type LeaseSignal struct {
	SystemID        string `json:"system_id"`
	IP              string `json:"ip"`
	MAC             string `json:"mac"`
	IsBootInterface bool   `json:"is_boot_interface"`
}

type BootAssetSignal struct {
	SystemID  string `json:"system_id"`
	BootAsset string `json:"boot_asset"`
}

type CurtinDownloadSignal struct {
	SystemID string `json:"system_id"`
}

type CurtinFinishedSignal struct {
	SystemID string `json:"system_id"`
}

type CloudInitDownloaded struct {
	SystemID string `json:"system_id"`
}

type CloudInitFinished struct {
	SystemID string `json:"system_id"`
}

func HandleSignal[T any](ctx workflow.Context, channel string) (*T, error) {
	var signal T

	sigChan := workflow.GetSignalChannel(ctx, channel)
	if !sigChan.Receive(ctx, &signal) {
		return nil, ErrSignalClosed
	}

	return &signal, nil
}
