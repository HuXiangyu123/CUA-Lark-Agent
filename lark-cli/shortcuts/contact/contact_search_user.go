// Copyright (c) 2026 Lark Technologies Pte. Ltd.
// SPDX-License-Identifier: MIT

package contact

import (
	"context"
	"fmt"
	"io"
	"math"
	"strconv"

	"github.com/larksuite/cli/internal/output"
	"github.com/larksuite/cli/shortcuts/common"
)

var ContactSearchUser = common.Shortcut{
	Service:     "contact",
	Command:     "+search-user",
	Description: "Search users (results sorted by relevance)",
	Risk:        "read",
	Scopes:      []string{"contact:user:search"},
	AuthTypes:   []string{"user"},
	HasFormat:   true,
	Flags: []common.Flag{
		{Name: "query", Desc: "search keyword", Required: true},
		{Name: "page-size", Default: "20", Desc: "page size"},
		{Name: "page-token", Desc: "page token"},
	},
	Validate: func(ctx context.Context, runtime *common.RuntimeContext) error {
		if len(runtime.Str("query")) == 0 {
			return common.FlagErrorf("search keyword empty")
		}
		return nil
	},
	DryRun: func(ctx context.Context, runtime *common.RuntimeContext) *common.DryRunAPI {
		pageSizeStr := runtime.Str("page-size")
		pageToken := runtime.Str("page-token")

		pageSize := 20
		if n, err := strconv.Atoi(pageSizeStr); err == nil {
			pageSize = int(math.Min(math.Max(float64(n), 1), 200))
		}

		params := map[string]interface{}{
			"query":     runtime.Str("query"),
			"page_size": pageSize,
		}
		if pageToken != "" {
			params["page_token"] = pageToken
		}

		return common.NewDryRunAPI().
			GET("/open-apis/search/v1/user").
			Params(params)
	},
	Execute: func(ctx context.Context, runtime *common.RuntimeContext) error {
		query := runtime.Str("query")
		pageSizeStr := runtime.Str("page-size")
		pageToken := runtime.Str("page-token")

		pageSize := 20
		if n, err := strconv.Atoi(pageSizeStr); err == nil {
			pageSize = int(math.Min(math.Max(float64(n), 1), 200))
		}

		params := map[string]interface{}{
			"query":     query,
			"page_size": pageSize,
		}
		if pageToken != "" {
			params["page_token"] = pageToken
		}

		data, err := runtime.CallAPI("GET", "/open-apis/search/v1/user", params, nil)
		if err != nil {
			return err
		}
		users, _ := data["users"].([]interface{})

		for _, u := range users {
			if m, _ := u.(map[string]interface{}); m != nil {
				if av, _ := m["avatar"].(map[string]interface{}); av != nil {
					m["avatar"] = map[string]interface{}{"avatar_origin": av["avatar_origin"]}
				}
			}
		}
		searchData := map[string]interface{}{
			"users":      users,
			"has_more":   data["has_more"],
			"page_token": data["page_token"],
		}
		runtime.OutFormat(searchData, nil, func(w io.Writer) {
			if len(users) == 0 {
				fmt.Fprintln(w, "No matching users found.")
				return
			}

			var rows []map[string]interface{}
			for _, u := range users {
				m, _ := u.(map[string]interface{})
				rows = append(rows, map[string]interface{}{
					"name":             pickUserName(m),
					"open_id":          m["open_id"],
					"email":            firstNonEmpty(m, "email", "mail"),
					"mobile":           firstNonEmpty(m, "mobile", "phone"),
					"department":       firstNonEmpty(m, "department_name", "department"),
					"enterprise_email": firstNonEmpty(m, "enterprise_email"),
				})
			}
			output.PrintTable(w, rows)
			hasMore, _ := data["has_more"].(bool)
			moreHint := ""
			if hasMore {
				pt, _ := data["page_token"].(string)
				moreHint = fmt.Sprintf(" (more available, page_token: %s)", pt)
			}
			fmt.Fprintf(w, "\n%d user(s)%s\n", len(users), moreHint)
		})
		return nil
	},
}

func pickUserName(m map[string]interface{}) string {
	for _, key := range []string{"name", "user_name", "display_name", "employee_name", "cn_name"} {
		if v, ok := m[key].(string); ok && v != "" {
			return v
		}
	}
	return ""
}

func firstNonEmpty(m map[string]interface{}, keys ...string) string {
	for _, key := range keys {
		if v, ok := m[key].(string); ok && v != "" {
			return v
		}
	}
	return ""
}
