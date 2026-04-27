// Copyright (c) 2026 Lark Technologies Pte. Ltd.
// SPDX-License-Identifier: MIT

package sheets

import (
	"context"
	"fmt"

	"github.com/larksuite/cli/internal/validate"
	"github.com/larksuite/cli/shortcuts/common"
)

var SheetRead = common.Shortcut{
	Service:     "sheets",
	Command:     "+read",
	Description: "Read spreadsheet cell values",
	Risk:        "read",
	Scopes:      []string{"sheets:spreadsheet:read"},
	AuthTypes:   []string{"user", "bot"},
	Flags: []common.Flag{
		{Name: "url", Desc: "spreadsheet URL"},
		{Name: "spreadsheet-token", Desc: "spreadsheet token"},
		{Name: "range", Desc: "read range (<sheetId>!A1:D10, A1:D10 with --sheet-id, or a single cell like C2)"},
		{Name: "sheet-id", Desc: "sheet ID"},
		{Name: "value-render-option", Desc: "render option: ToString|FormattedValue|Formula|UnformattedValue"},
	},
	Validate: func(ctx context.Context, runtime *common.RuntimeContext) error {
		token := runtime.Str("spreadsheet-token")
		if runtime.Str("url") != "" {
			token = extractSpreadsheetToken(runtime.Str("url"))
		}
		if token == "" {
			return common.FlagErrorf("specify --url or --spreadsheet-token")
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
		readRange := runtime.Str("range")
		if readRange == "" && runtime.Str("sheet-id") != "" {
			readRange = runtime.Str("sheet-id")
		}
		readRange = normalizePointRange(runtime.Str("sheet-id"), readRange)
		return common.NewDryRunAPI().
			GET("/open-apis/sheets/v2/spreadsheets/:token/values/:range").
			Set("token", token).Set("range", readRange)
	},
	Execute: func(ctx context.Context, runtime *common.RuntimeContext) error {
		token := runtime.Str("spreadsheet-token")
		if runtime.Str("url") != "" {
			token = extractSpreadsheetToken(runtime.Str("url"))
		}

		readRange := runtime.Str("range")
		if readRange == "" && runtime.Str("sheet-id") != "" {
			readRange = runtime.Str("sheet-id")
		}

		if readRange == "" {
			var err error
			readRange, err = getFirstSheetID(runtime, token)
			if err != nil {
				return err
			}
		}
		readRange = normalizePointRange(runtime.Str("sheet-id"), readRange)

		params := map[string]interface{}{}
		renderOption := runtime.Str("value-render-option")
		if renderOption != "" {
			params["valueRenderOption"] = renderOption
		}

		data, err := runtime.CallAPI("GET", fmt.Sprintf("/open-apis/sheets/v2/spreadsheets/%s/values/%s", validate.EncodePathSegment(token), validate.EncodePathSegment(readRange)), params, nil)
		if err != nil {
			return err
		}
		runtime.Out(data, nil)
		return nil
	},
}
