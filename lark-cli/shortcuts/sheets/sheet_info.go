// Copyright (c) 2026 Lark Technologies Pte. Ltd.
// SPDX-License-Identifier: MIT

package sheets

import (
	"context"
	"fmt"

	"github.com/larksuite/cli/internal/validate"
	"github.com/larksuite/cli/shortcuts/common"
)

var SheetInfo = common.Shortcut{
	Service:     "sheets",
	Command:     "+info",
	Description: "View spreadsheet and sheet information",
	Risk:        "read",
	Scopes:      []string{"sheets:spreadsheet:read"},
	AuthTypes:   []string{"user", "bot"},
	Flags: []common.Flag{
		{Name: "url", Desc: "spreadsheet URL"},
		{Name: "spreadsheet-token", Desc: "spreadsheet token"},
	},
	Validate: func(ctx context.Context, runtime *common.RuntimeContext) error {
		token := runtime.Str("spreadsheet-token")
		if runtime.Str("url") != "" {
			token = extractSpreadsheetToken(runtime.Str("url"))
		}
		if token == "" {
			return common.FlagErrorf("specify --url or --spreadsheet-token")
		}
		return nil
	},
	DryRun: func(ctx context.Context, runtime *common.RuntimeContext) *common.DryRunAPI {
		token := runtime.Str("spreadsheet-token")
		if runtime.Str("url") != "" {
			token = extractSpreadsheetToken(runtime.Str("url"))
		}
		return common.NewDryRunAPI().
			GET("/open-apis/sheets/v3/spreadsheets/:token").
			Set("token", token)
	},
	Execute: func(ctx context.Context, runtime *common.RuntimeContext) error {
		token := runtime.Str("spreadsheet-token")
		if runtime.Str("url") != "" {
			token = extractSpreadsheetToken(runtime.Str("url"))
		}

		// Get spreadsheet info
		spreadsheetData, err := runtime.CallAPI("GET", fmt.Sprintf("/open-apis/sheets/v3/spreadsheets/%s", validate.EncodePathSegment(token)), nil, nil)
		if err != nil {
			return err
		}

		// Get sheets info (best-effort)
		var sheetsData interface{}
		sheetsResult, sheetsErr := runtime.RawAPI("GET", fmt.Sprintf("/open-apis/sheets/v3/spreadsheets/%s/sheets/query", validate.EncodePathSegment(token)), nil, nil)
		if sheetsErr == nil {
			if sheetsMap, ok := sheetsResult.(map[string]interface{}); ok {
				if d, ok := sheetsMap["data"].(map[string]interface{}); ok {
					sheetsData = d
				}
			}
		}

		runtime.Out(map[string]interface{}{
			"spreadsheet": spreadsheetData,
			"sheets":      sheetsData,
		}, nil)
		return nil
	},
}
