// Copyright (c) 2023-2024 Canonical Ltd
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

package netmon

import (
	"context"
	"net"
	"net/netip"
	"os"
	"strings"
	"testing"

	"github.com/google/gopacket"
	"github.com/google/gopacket/layers"
	"github.com/stretchr/testify/assert"
)

// TestScan can be used for testing
// sudo is required because Scan is using privileged ping
// sudo TEST_NETMON_SCAN=172.16.1.1,172.16.2.1 \
// go test maas.io/core/src/maasagent/internal/netmon -run TestScan -count 1 -v
func TestScan(t *testing.T) {
	env := os.Getenv("TEST_NETMON_SCAN")
	if env == "" {
		t.Skip("set TEST_NETMON_SCAN to run this test")
	}

	var ips []netip.Addr

	for _, v := range strings.Split(env, ",") {
		ips = append(ips, netip.MustParseAddr(v))
	}

	result, err := Scan(context.TODO(), ips)
	if err != nil {
		t.Fatal(err)
	}

	t.Logf("%v\n", result)
}

func TestGetIPHwAddressPair(t *testing.T) {
	testcases := map[string]struct {
		in  []byte
		out IPHwAddressPair
	}{
		"test IPv4 address": {
			in: []byte{
				0xc0, 0x25, 0xa5, 0x8d, 0xd0, 0x68, 0xcc, 0x2d, 0xe0, 0xe7, 0x03, 0xf0,
				0x08, 0x00, 0x45, 0x00, 0x00, 0x1c, 0x73, 0x72, 0x00, 0x00, 0x38, 0x01,
				0x60, 0x52, 0x01, 0x01, 0x01, 0x01, 0xac, 0x10, 0x01, 0x0b, 0x00, 0x00,
				0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
				0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
			},
			out: IPHwAddressPair{
				IP:        netip.MustParseAddr("1.1.1.1"),
				HwAddress: net.HardwareAddr([]byte{0xcc, 0x2d, 0xe0, 0xe7, 0x03, 0xf0}),
			},
		},
		"test IPv6 address": {
			in: []byte{
				0x00, 0x16, 0x3e, 0xe5, 0x09, 0xa6, 0x00, 0x16, 0x3e, 0xbc, 0x34, 0x46,
				0x86, 0xdd, 0x60, 0x0d, 0xf8, 0xb4, 0x00, 0x08, 0x3a, 0x40, 0xfd, 0x42,
				0x9f, 0xe5, 0x65, 0x93, 0xce, 0x63, 0x02, 0x16, 0x3e, 0xff, 0xfe, 0xbc,
				0x34, 0x46, 0xfd, 0x42, 0x9f, 0xe5, 0x65, 0x93, 0xce, 0x63, 0x00, 0x00,
				0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x81, 0x00, 0x68, 0x64, 0x00, 0x00,
				0x00, 0x00,
			},
			out: IPHwAddressPair{
				IP:        netip.MustParseAddr("fd42:9fe5:6593:ce63:216:3eff:febc:3446"),
				HwAddress: net.HardwareAddr([]byte{0x00, 0x16, 0x3e, 0xbc, 0x34, 0x46}),
			},
		},
	}

	for name, tc := range testcases {
		tc := tc

		t.Run(name, func(t *testing.T) {
			t.Parallel()

			packet := gopacket.NewPacket(tc.in, layers.LayerTypeEthernet, gopacket.Default)

			res := getIPHwAddressPair(packet)
			assert.Equal(t, tc.out, res)
		})
	}
}
