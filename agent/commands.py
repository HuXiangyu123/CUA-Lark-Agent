"""
Registry of all available lark-cli shortcut commands with descriptions and usage patterns.
This is passed to the LLM as context so it knows what tools it has available.
"""

COMMANDS = {
    # ── Calendar ──────────────────────────────────────────────
    "calendar +agenda": {
        "desc": "View upcoming calendar events (defaults to today). Output is a list of events with times.",
        "example": 'lark-cli calendar +agenda --start "2026-04-27" --end "2026-04-28"',
        "args": [
            "--start <ISO8601>   # start time (default: today start)",
            "--end <ISO8601>     # end time (default: today end)",
            "--calendar-id <id>  # calendar ID (default: primary)",
            "--as <user|bot>     # identity (default: user)",
        ],
    },
    "calendar +create": {
        "desc": "Create a calendar event and optionally invite attendees.",
        "example": 'lark-cli calendar +create --summary "Team sync" --start "2026-04-27T10:00:00" --end "2026-04-27T11:00:00" --attendee-ids "ou_xxx"',
        "args": [
            "--summary <str>       # event title (required)",
            "--start <ISO8601>     # start time (required)",
            "--end <ISO8601>       # end time (required)",
            "--description <str>  # event description",
            "--attendee-ids <csv>  # comma-separated open_ids (ou_xxx)",
            "--calendar-id <id>    # calendar ID (default: primary)",
            "--as <user|bot>       # identity (default: user)",
        ],
    },
    "calendar +freebusy": {
        "desc": "Query free/busy status and RSVP status for one or more users.",
        "example": 'lark-cli calendar +freebusy --user-ids "ou_xxx" --start "2026-04-27T09:00:00" --end "2026-04-27T18:00:00"',
        "args": [
            "--user-ids <csv>  # comma-separated open_ids",
            "--start <ISO8601> # start time (required)",
            "--end <ISO8601>   # end time (required)",
        ],
    },
    "calendar +room-find": {
        "desc": "Find available meeting rooms for given time slots.",
        "example": 'lark-cli calendar +room-find --room-ids "omm_xxx" --start "2026-04-27T10:00:00" --end "2026-04-27T11:00:00"',
        "args": [
            "--room-ids <csv>  # room IDs",
            "--start <ISO8601> # start time (required)",
            "--end <ISO8601>   # end time (required)",
        ],
    },
    "calendar +rsvp": {
        "desc": "Reply to a calendar event (accept / decline / tentative).",
        "example": 'lark-cli calendar +rsvp --event-id "oc_xxx" --calendar-id "primary" --action accept',
        "args": [
            "--event-id <id>     # event ID (required)",
            "--calendar-id <id>   # calendar ID (default: primary)",
            "--action <str>       # accept | decline | tentative (required)",
        ],
    },
    "calendar +suggestion": {
        "desc": "Intelligently suggest available time slots based on attendee calendars.",
        "example": 'lark-cli calendar +suggestion --user-ids "ou_xxx,ou_yyy" --duration 60',
        "args": [
            "--user-ids <csv>  # comma-separated open_ids",
            "--duration <int>   # meeting duration in minutes",
        ],
    },
    "calendar event.attendees": {
        "desc": "List or manage attendees of a calendar event.",
        "example": 'lark-cli calendar event.attendees list --event-id "oc_xxx" --calendar-id "primary"',
        "args": [
            "--event-id <id>   # event ID (required)",
            "--calendar-id <id> # calendar ID (default: primary)",
        ],
    },
    # ── IM / Messaging ─────────────────────────────────────────
    "im +messages-send": {
        "desc": "Send a text/markdown message to a chat (group) or direct message (P2P).",
        "example": 'lark-cli im +messages-send --chat-id "oc_xxx" --text "Hello from CLI!"',
        "args": [
            "--chat-id <id>       # group chat ID oc_xxx (mutually exclusive with --user-id)",
            "--user-id <id>       # recipient open_id ou_xxx (mutually exclusive with --chat-id)",
            "--text <str>         # plain text message",
            "--markdown <str>    # markdown message (rendered as Lark post)",
            "--content <json>     # raw message content JSON",
            "--msg-type <type>    # text | post | image | file | markdown (default: text)",
            "--idempotency-key <str> # prevent duplicate sends",
            "--as <bot|user>      # identity (default: bot)",
        ],
    },
    "im +messages-reply": {
        "desc": "Reply to a specific message (in a thread).",
        "example": 'lark-cli im +messages-reply --message-id "om_xxx" --text "Got it!"',
        "args": [
            "--message-id <id>    # message ID to reply to (om_xxx)",
            "--text <str>         # reply text",
            "--markdown <str>     # reply markdown",
            "--as <bot|user>      # identity (default: bot)",
        ],
    },
    "im +chat-search": {
        "desc": "Search visible group chats by name and/or member.",
        "example": 'lark-cli im +chat-search --query "test"',
        "args": [
            "--query <str>        # keyword to search",
            "--member-ids <csv>  # filter by member open_ids",
        ],
    },
    "im +chat-create": {
        "desc": "Create a group chat, optionally inviting members.",
        "example": 'lark-cli im +chat-create --name "Test Group" --user-ids "ou_xxx"',
        "args": [
            "--name <str>         # group name",
            "--description <str>",
            "--user-ids <csv>    # initial members (open_ids)",
            "--bot-manager <id>   # bot manager open_id",
        ],
    },
    "im +chat-messages-list": {
        "desc": "List messages in a chat or P2P conversation.",
        "example": 'lark-cli im +chat-messages-list --chat-id "oc_xxx" --page-size 20',
        "args": [
            "--chat-id <id>      # chat ID (oc_xxx)",
            "--user-id <id>      # P2P: user open_id",
            "--page-size <n>     # page size (default: 20)",
            "--sort-type <str>   # ByCreateTimeDescend | ByCreateTimeAscend",
        ],
    },
    "im +messages-search": {
        "desc": "Search messages across all chats by keyword.",
        "example": 'lark-cli im +messages-search --query "hello" --page-size 10',
        "args": [
            "--query <str>       # search keyword",
            "--chat-id <id>      # limit to specific chat",
            "--user-id <id>      # limit to messages from specific user",
            "--start-time <ts>   # Unix timestamp",
            "--end-time <ts>     # Unix timestamp",
        ],
    },
    "im +messages-resources-download": {
        "desc": "Download images/files from a message.",
        "example": 'lark-cli im +messages-resources-download --message-id "om_xxx" --file-key "file_key_xxx" --output "./downloads/"',
        "args": [
            "--message-id <id>   # message ID (om_xxx)",
            "--file-key <key>    # file key from message content",
            "--output <path>     # output directory",
        ],
    },
    "im +chat-update": {
        "desc": "Update group chat name or description.",
        "example": 'lark-cli im +chat-update --chat-id "oc_xxx" --name "New Name"',
        "args": [
            "--chat-id <id>",
            "--name <str>",
            "--description <str>",
        ],
    },
    "im +threads-messages-list": {
        "desc": "List all messages in a thread.",
        "example": 'lark-cli im +threads-messages-list --thread-id "oc_xxx"',
        "args": [
            "--thread-id <id>   # thread/chat ID (oc_xxx)",
            "--page-size <n>",
        ],
    },
    "im reactions": {
        "desc": "Add or remove emoji reactions on a message.",
        "example": 'lark-cli im reactions add --message-id "om_xxx" --reaction-type "SMILE"',
        "args": [
            "--message-id <id>",
            "--reaction-type <str>  # emoji type",
            "add|remove",
        ],
    },
    # ── Docs / Cloud Documents ─────────────────────────────────
    "docs +create": {
        "desc": "Create a new Lark document, optionally with markdown content.",
        "example": 'lark-cli docs +create --title "My Doc" --markdown "# Hello\\n\\nWorld"',
        "args": [
            "--title <str>           # document title",
            "--markdown <content>    # markdown body content",
            "--folder-token <token>  # parent folder",
            "--wiki-space <id>      # wiki space ID",
            "--as <user|bot>         # identity (default: user)",
        ],
    },
    "docs +fetch": {
        "desc": "Fetch document content (text blocks).",
        "example": 'lark-cli docs +fetch --doc-token "WqDxxx"',
        "args": [
            "--doc-token <token>  # document token",
        ],
    },
    "docs +update": {
        "desc": "Update document content (insert/replace blocks).",
        "example": 'lark-cli docs +update --doc-token "WqDxxx" --markdown "\\n## New Section\\n"',
        "args": [
            "--doc-token <token>",
            "--markdown <content>",
        ],
    },
    "docs +search": {
        "desc": "Search Lark docs, Wiki, and spreadsheets.",
        "example": 'lark-cli docs +search --query "project report"',
        "args": [
            "--query <str>",
        ],
    },
    "docs +media-insert": {
        "desc": "Insert a local image or file into a document.",
        "example": 'lark-cli docs +media-insert --doc-token "WqDxxx" --file "./photo.png"',
        "args": [
            "--doc-token <token>",
            "--file <path>    # local file path",
        ],
    },
    "docs +media-upload": {
        "desc": "Upload media file to a document block.",
        "example": 'lark-cli docs +media-upload --doc-token "WqDxxx" --file "./doc.pdf"',
        "args": [
            "--doc-token <token>",
            "--file <path>",
        ],
    },
    # ── Drive / Cloud Space ────────────────────────────────────
    "drive +files-list": {
        "desc": "List files in a folder.",
        "example": 'lark-cli drive +files-list --folder-token "bafxxx"',
        "args": [
            "--folder-token <token>  # folder token (default: root)",
            "--page-size <n>",
        ],
    },
    "drive +file-download": {
        "desc": "Download a file from Drive.",
        "example": 'lark-cli drive +file-download --file-token "bafxxx" --output "./downloads/"',
        "args": [
            "--file-token <token>",
            "--output <path>",
        ],
    },
    # ── Sheets / Spreadsheets ──────────────────────────────────
    "sheets spreadsheet": {
        "desc": "Create a spreadsheet.",
        "example": 'lark-cli sheets spreadsheet create --title "Tracking Sheet"',
        "args": [
            "--title <str>",
            "--folder-token <token>",
        ],
    },
    "sheets read": {
        "desc": "Read cell values from a sheet.",
        "example": 'lark-cli sheets read --spreadsheet-id "shtxxx" --sheet-id "0"',
        "args": [
            "--spreadsheet-id <id>",
            "--sheet-id <id>       # sheet tab ID",
            "--range <str>         # e.g. A1:D10",
        ],
    },
    "sheets write": {
        "desc": "Write values to cells.",
        "example": 'lark-cli sheets write --spreadsheet-id "shtxxx" --sheet-id "0" --values "[[\\"Name\\", \\"Value\\"]]"',
        "args": [
            "--spreadsheet-id <id>",
            "--sheet-id <id>",
            "--values <json>",
            "--range <str>",
        ],
    },
    # ── Base / Multi-dimensional Tables ───────────────────────
    "base +tables-list": {
        "desc": "List all tables in a Base app.",
        "example": 'lark-cli base +tables-list --app-token "bascxxx"',
        "args": [
            "--app-token <token>  # Base app token",
        ],
    },
    "base +records-list": {
        "desc": "List records in a Base table.",
        "example": 'lark-cli base +records-list --app-token "bascxxx" --table-id "tblxxx" --page-size 20',
        "args": [
            "--app-token <token>",
            "--table-id <id>",
            "--page-size <n>",
        ],
    },
    "base +record-create": {
        "desc": "Create a record in a Base table.",
        "example": 'lark-cli base +record-create --app-token "bascxxx" --table-id "tblxxx" --fields "\\"{\\\\\\"Name\\\\\\":\\\\\\"Test\\\\\\"}\""',
        "args": [
            "--app-token <token>",
            "--table-id <id>",
            "--fields <json>",
        ],
    },
    # ── Contact ───────────────────────────────────────────────
    "contact +search-user": {
        "desc": "Search for users by name or email.",
        "example": 'lark-cli contact +search-user --query "zhang san"',
        "args": [
            "--query <str>",
        ],
    },
    "contact users": {
        "desc": "Get user info by open_id.",
        "example": 'lark-cli contact users get --user-id "ou_xxx"',
        "args": [
            "--user-id <id>",
        ],
    },
    "contact departments": {
        "desc": "List or get department info.",
        "example": 'lark-cli contact departments get --department-id "d_xxx"',
        "args": [
            "--department-id <id>",
        ],
    },
    # ── Mail ───────────────────────────────────────────────────
    "mail +messages-list": {
        "desc": "List emails in a folder.",
        "example": 'lark-cli mail +messages-list --folder-id "INBOX" --page-size 20',
        "args": [
            "--folder-id <id>     # INBOX, SENT, DRAFT, etc.",
            "--page-size <n>",
        ],
    },
    "mail +message-send": {
        "desc": "Send an email.",
        "example": 'lark-cli mail +message-send --to "test@example.com" --subject "Hello" --text "Body"',
        "args": [
            "--to <email>",
            "--cc <email>",
            "--subject <str>",
            "--text <str>",
            "--html <str>",
        ],
    },
    "mail +message-reply": {
        "desc": "Reply to an email.",
        "example": 'lark-cli mail +message-reply --message-id "om_xxx" --text "Thanks!"',
        "args": [
            "--message-id <id>",
            "--text <str>",
        ],
    },
    # ── Tasks ──────────────────────────────────────────────────
    "task +tasks-list": {
        "desc": "List tasks in a task list.",
        "example": 'lark-cli task +tasks-list --list-id "pvixxx"',
        "args": [
            "--list-id <id>",
        ],
    },
    "task +task-create": {
        "desc": "Create a task.",
        "example": 'lark-cli task +task-create --summary "Review doc" --due "2026-04-30"',
        "args": [
            "--summary <str>",
            "--description <str>",
            "--due <ISO8601>",
            "--member-ids <csv>   # assignee open_ids",
        ],
    },
    # ── VC / Video Conference ───────────────────────────────────
    "vc +meetings-list": {
        "desc": "List recent meetings.",
        "example": 'lark-cli vc +meetings-list --page-size 20',
        "args": [
            "--page-size <n>",
        ],
    },
    "vc +meeting-minutes": {
        "desc": "Get meeting minutes/summary.",
        "example": 'lark-cli vc +meeting-minutes --meeting-id "omm_xxx"',
        "args": [
            "--meeting-id <id>",
        ],
    },
    # ── OKR ────────────────────────────────────────────────────
    "okr +my-list": {
        "desc": "List user's OKRs.",
        "example": 'lark-cli okr +my-list --user-id "ou_xxx"',
        "args": [
            "--user-id <id>",
        ],
    },
    # ── Wiki ───────────────────────────────────────────────────
    "wiki +nodes-list": {
        "desc": "List wiki space nodes.",
        "example": 'lark-cli wiki +nodes-list --space-id "700xxx"',
        "args": [
            "--space-id <id>",
        ],
    },
    "wiki +node-get": {
        "desc": "Get wiki node info.",
        "example": 'lark-cli wiki +node-get --node-token "WqDxxx"',
        "args": [
            "--node-token <token>",
        ],
    },
    # ── Generic API ────────────────────────────────────────────
    "api": {
        "desc": "Call any Lark Open Platform API directly.",
        "example": 'lark-cli api GET /open-apis/calendar/v4/calendars/primary/events --params \'{"start_time":"1700000000","end_time":"1700086400"}\'',
        "args": [
            "<GET|POST|PUT|PATCH|DELETE>",
            "<API path>",
            "--params <json>    # URL query parameters",
            "--data <json>      # request body",
            "--as <user|bot>",
        ],
    },
}

# Format the full command registry as a string for the system prompt
def format_registry() -> str:
    lines = []
    for cmd, info in COMMANDS.items():
        lines.append(f"\n## {cmd}")
        lines.append(f"Description: {info['desc']}")
        if info["args"]:
            lines.append("Arguments:")
            for arg in info["args"]:
                lines.append(f"  {arg}")
        if info["example"]:
            lines.append(f"Example: {info['example']}")
    return "\n".join(lines)


# Low-level API registry (raw API commands)
API_COMMANDS = """
## Low-level API access
Use `lark-cli api <METHOD> <PATH> [--params <json>] [--data <json>] [--as user|bot]`
to call any Lark Open Platform API. Examples:
  lark-cli api GET /open-apis/calendar/v4/calendars
  lark-cli api POST /open-apis/im/v1/messages --data '{"receive_id":"oc_xxx","msg_type":"text","content":"{\\"text\\":\\"Hello\\"}"}'
  lark-cli api GET /open-apis/drive/v1/files --params '{"folder_token":"bafxxx"}'
"""
