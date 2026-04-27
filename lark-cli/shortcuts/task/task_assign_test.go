// Copyright (c) 2026 Lark Technologies Pte. Ltd.
// SPDX-License-Identifier: MIT

package task

import (
	"testing"

	"github.com/smartystreets/goconvey/convey"
)

func TestBuildMembersBody(t *testing.T) {
	convey.Convey("Build with ids and token", t, func() {
		body := buildMembersBody("u1, u2 , ", "token1")
		members := body["members"].([]map[string]interface{})
		convey.So(len(members), convey.ShouldEqual, 2)
		convey.So(body["client_token"], convey.ShouldEqual, "token1")
	})
}
