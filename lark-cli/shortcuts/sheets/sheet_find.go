// Copyright (c) 2026 Lark Technologies Pte. Ltd.
// SPDX-License-Identifier: MIT

package sheets

import (
	"context"
	"fmt"

	"github.com/larksuite/cli/internal/validate"
	"github.com/larksuite/cli/shortcuts/common"
)

var SheetFind = common.Shortcut{
	Service:     "sheets",
	Command:     "+find",
	Description: "Find cells in a spreadsheet",
	Risk:        "read",
	Scopes:      []string{"sheets:spreadsheet:read"},
	AuthTypes:   []string{"user", "bot"},
	Flags: []common.Flag{
		{Name: "url", Desc: "spreadsheet URL"},
		{Name: "spreadsheet-token", Desc: "spreadsheet token"},
		{Name: "sheet-id", Desc: "sheet ID", Required: true},
		{Name: "find", Desc: "search text", Required: true},
		{Name: "range", Desc: "search range (<sheetId>!A1:D10, or A1:D10 / C2 with --sheet-id)"},
		{Name: "ignore-case", Type: "bool", Desc: "case-insensitive search"},
		{Name: "match-entire-cell", Type: "bool", Desc: "match entire cell"},
		{Name: "search-by-regex", Type: "bool", Desc: "regex search"},
		{Name: "include-formulas", Type: "bool", Desc: "search formulas"},
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
		sheetIdFlag := runtime.Str("sheet-id")
		findCondition := map[string]interface{}{
			"range":             sheetIdFlag,
			"match_case":        !runtime.Bool("ignore-case"),
			"match_entire_cell": runtime.Bool("match-entire-cell"),
			"search_by_regex":   runtime.Bool("search-by-regex"),
			"include_formulas":  runtime.Bool("include-formulas"),
		}
		if runtime.Str("range") != "" {
			findCondition["range"] = normalizePointRange(sheetIdFlag, runtime.Str("range"))
		}
		return common.NewDryRunAPI().
			POST("/open-apis/sheets/v3/spreadsheets/:token/sheets/:sheet_id/find").
			Body(map[string]interface{}{
				"find":           runtime.Str("find"),
				"find_condition": findCondition,
			}).
			Set("token", token).Set("sheet_id", sheetIdFlag).Set("find", runtime.Str("find"))
	},
	Execute: func(ctx context.Context, runtime *common.RuntimeContext) error {
		token := runtime.Str("spreadsheet-token")
		if runtime.Str("url") != "" {
			token = extractSpreadsheetToken(runtime.Str("url"))
		}

		sheetIdFlag := runtime.Str("sheet-id")
		findText := runtime.Str("find")

		findCondition := map[string]interface{}{
			"range":             sheetIdFlag,
			"match_case":        !runtime.Bool("ignore-case"),
			"match_entire_cell": runtime.Bool("match-entire-cell"),
			"search_by_regex":   runtime.Bool("search-by-regex"),
			"include_formulas":  runtime.Bool("include-formulas"),
		}
		if runtime.Str("range") != "" {
			findCondition["range"] = normalizePointRange(sheetIdFlag, runtime.Str("range"))
		}

		reqData := map[string]interface{}{
			"find_condition": findCondition,
			"find":           findText,
		}

		data, err := runtime.CallAPI("POST", fmt.Sprintf("/open-apis/sheets/v3/spreadsheets/%s/sheets/%s/find", validate.EncodePathSegment(token), validate.EncodePathSegment(sheetIdFlag)), nil, reqData)
		if err != nil {
			return err
		}
		runtime.Out(data, nil)
		return nil
	},
}
