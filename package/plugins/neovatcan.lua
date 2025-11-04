plugin_metadata = {
    name = "VATCAN Event Plugin",
    version = "1.0",
    author = "neoradar",
}

EVENT_CODE = "19tiq"

VATCAN_API_URL = "https://bookings.vatcan.ca/api/event/" .. EVENT_CODE
function GET_SLURPER_URL(cid) return "https://slurper.vatsim.net/users/info?cid=" .. cid end

COUNTER = 0

VATCAN_TAG_ID = nil

PROCESSED_AIRCRAFT = {}
CURRENT_VATCAN_DATA = {}

function Init()
    local testItemDef = TagItemDefinition.new();
    testItemDef.name = "VATCAN Event Status"
    testItemDef.defaultValue = ""
    testItemDef.allowedActions = {}

    local tagInterface = nr.tag:getInterface()
    VATCAN_TAG_ID = tagInterface:RegisterTagItem(testItemDef)
    logger:info("Registered VATCAN tag with ID: " .. tostring(VATCAN_TAG_ID))

    logger:info("VATCAN Plugin initialized.")
end

local function update_tag_for_callsign(callsign, cid)
    if not CURRENT_VATCAN_DATA or not VATCAN_TAG_ID then
        return
    end

    local aircraft = nr.aircraft:getByCallsign(callsign)
    if not aircraft then
        logger:info("Aircraft with callsign " .. callsign .. " not found in FSD.")
        PROCESSED_AIRCRAFT[callsign] = false
        return
    end

    if PROCESSED_AIRCRAFT[callsign] then
        return
    end

    local tagContext = TagContext.new()
    tagContext.colour = { 255, 172, 28 } -- Orange color
    tagContext.callsign = callsign

    nr.tag:getInterface():UpdateTagValue(VATCAN_TAG_ID, "EVENT", tagContext)

    PROCESSED_AIRCRAFT[callsign] = true

    logger:info("Tagged aircraft " .. callsign .. " with VATCAN event.")
end

local function update_cid_callsign_match_callback(status, body)
    if not status == 200 then
        logger:error("Failed to fetch data from Slurper: HTTP " .. tostring(status))
        return
    end

    if not body or body == "" then
        return
    end

    --- Format is 810425,SBR1,pilot,,,26.18311,-87.86074,0,0,0,0,0,0,0,0,
    local fields = {}
    for field in string.gmatch(body, '([^,]+)') do
        table.insert(fields, field)
    end

    if #fields < 3 then
        logger:error("Unexpected response format from Slurper: " .. body)
        return
    end

    local cid = tonumber(fields[1])
    local callsign = fields[2]
    if cid and callsign then
        CURRENT_VATCAN_DATA[cid] = callsign
        update_tag_for_callsign(callsign, cid)
    end
end

local function update_vatcan_data_callback(status, body)
    if not status == 200 then
        logger:error("Failed to fetch data from VATCAN: HTTP " .. tostring(status))
        return
    end

    local decoded_data = from_json(body)

    if not decoded_data then
        logger:error("Failed to decode JSON response from VATCAN.")
        return
    end

    -- Convert array to CID-indexed lookup table
    CURRENT_VATCAN_DATA = {}
    for idx, entry in pairs(decoded_data) do
        if entry.cid then
            CURRENT_VATCAN_DATA[entry.cid] = nil
            logger:info("Fetching callsign for CID: " .. GET_SLURPER_URL(tostring(entry.cid)))
            http_get(GET_SLURPER_URL(tostring(entry.cid)), {}, update_cid_callsign_match_callback)
        end
    end

    logger:info("Fetched " .. tostring(#decoded_data) .. " entries from VATCAN.")
    logger:info("VATCAN data updated successfully.")
end

onTick = function()
    if not nr.fsd:getConnection() then
        PROCESSED_AIRCRAFT = {}
        CURRENT_VATCAN_DATA = {}
        return
    end

    if COUNTER == 0 or COUNTER % 600 == 0 then
        http_get(VATCAN_API_URL, {}, update_vatcan_data_callback)
    end

    if COUNTER % 120 == 0 then
        for cid, callsign in pairs(CURRENT_VATCAN_DATA) do
            if callsign then
                update_tag_for_callsign(callsign, cid)
            end
        end
    end

    COUNTER = COUNTER + 1
end

Init()
