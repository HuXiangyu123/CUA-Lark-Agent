// Copyright (c) 2026 Lark Technologies Pte. Ltd.
// SPDX-License-Identifier: MIT

package sheets

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/larksuite/cli/internal/validate"
	"github.com/larksuite/cli/shortcuts/common"
)

var SheetAppend = common.Shortcut{
	Service:     "sheets",
	Command:     "+append",
	Description: "Append rows to a spreadsheet",
	Risk:        "write",
	Scopes:      []string{"sheets:spreadsheet:write_only", "sheets:spreadsheet:read"},
	AuthTypes:   []string{"user", "bot"},
	Flags: []common.Flag{
		{Name: "url", Desc: "spreadsheet URL"},
		{Name: "spreadsheet-token", Desc: "spreadsheet token"},
		{Name: "range", Desc: "append range (<sheetId>!A1:D10, A1:D10 with --sheet-id, or a single cell like C2)"},
		{Name: "sheet-id", Desc: "sheet ID"},
		{Name: "values", Desc: "2D array JSON", Required: true},
	},
	Validate: func(ctx context.Context, runtime *common.RuntimeContext) error {
		token := runtime.Str("spreadsheet-token")
		if runtime.Str("url") != "" {
			token = extractSpreadsheetToken(runtime.Str("url"))
		}
		if token == "" {
			return common.FlagErrorf("specify --url or --spreadsheet-token")
		}

		var values interface{}
		if err := json.Unmarshal([]byte(runtime.Str("values")), &values); err != nil {
			return common.FlagErrorf("--values invalid JSON, must be a 2D array")
		}
		if err := validateSheetRangeInput(runtime.Str("sheet-id"), runtime.Str("range")); err != nil {
			return err
		}
		return nil
	},
	DryRun: func(ctx context.Context, runtime *common.RuntimeContext) *common.DryRunAPI {
		token := runtime.Str("spreadsheet-token")
		if runtime.Str("url") != "" {
			token = extractSpreadsheetToken(runtime.Str("url"))
		}
		appendRange := runtime.Str("range")
		if appendRange == "" && runtime.Str("sheet-id") != "" {
			appendRange = runtime.Str("sheet-id")
		}
		var values interface{}
		json.Unmarshal([]byte(runtime.Str("values")), &values)
		appendRange = normalizePointRange(runtime.Str("sheet-id"), appendRange)
		return common.NewDryRunAPI().
			POST("/open-apis/sheets/v2/spreadsheets/:token/values_append").
			Body(map[string]interface{}{"valueRange": map[string]interface{}{"range": appendRange, "values": values}}).
			Set("token", token)
	},
	Execute: func(ctx context.Context, runtime *common.RuntimeContext) error {
		token := runtime.Str("spreadsheet-token")
		if runtime.Str("url") != "" {
			token = extractSpreadsheetToken(runtime.Str("url"))
		}

		var values interface{}
		json.Unmarshal([]byte(runtime.Str("values")), &values)

		appendRange := runtime.Str("range")
		if appendRange == "" && runtime.Str("sheet-id") != "" {
			appendRange = runtime.Str("sheet-id")
		}

		if appendRange == "" {
			var err error
			appendRange, err = getFirstSheetID(runtime, token)
			if err != nil {
				return err
			}
		}
		appendRange = normalizePointRange(runtime.Str("sheet-id"), appendRange)

		data, err := runtime.CallAPI("POST", fmt.Sprintf("/open-apis/sheets/v2/spreadsheets/%s/values_append", validate.EncodePathSegment(token)), nil, map[string]interface{}{
			"valueRange": map[string]interface{}{
				"range":  appendRange,
				"values": values,
			},
		})
		if err != nil {
			return err
		}
		runtime.Out(data, nil)
		return nil
	},
}
