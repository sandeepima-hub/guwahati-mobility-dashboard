"""
config.py
=========
Single source of truth for all corridor stops, peak windows, API settings,
and audit thresholds.

LOS Framework: Indo-HCM 2017 (CSIR-CRRI), New Delhi.
Primary measure: PTI (Planning Time Index) per Table 10.7 —
Reliability LOS for Interrupted 4-Lane Divided Urban Road using Car Travel Time.
IIT Guwahati was a Regional Coordinator for Indo-HCM.
"""

# ── Peak Windows ──────────────────────────────────────────────────────────────
PEAK_WINDOWS = {
    "AM": {"label": "AM Peak", "start_hour": 8,  "end_hour": 10},
    "PM": {"label": "PM Peak", "start_hour": 17, "end_hour": 19},
}

SAMPLE_INTERVAL_MINUTES = 30

# ── Free-Flow Reference ───────────────────────────────────────────────────────
FREE_FLOW_SPEED_KMPH = 40.0
FREE_FLOW_HOUR       = 6

# ── Indo-HCM 2017 LOS Thresholds ─────────────────────────────────────────────
# Source: CSIR-CRRI, Indian Highway Capacity Manual (Indo-HCM), 2017.

# Table 10.7 — PTI-based LOS for Cars on Interrupted 4-Lane Divided Urban Road
# (Section 10.16, p.10-14) — primary LOS measure for GS Road and NH37
PTI_LOS_THRESHOLDS = {
    "A": (0.00, 1.10),
    "B": (1.10, 1.40),
    "C": (1.40, 1.60),
    "D": (1.60, 1.80),
    "E": (1.80, float("inf")),
}

# Table 5.7 — % Free Flow Speed LOS for Multilane Divided Urban Roads
# (Section 5.4.6, p.5-14)
FFS_LOS_THRESHOLDS = {
    "A": (84,  100),
    "B": (76,   84),
    "C": (59,   76),
    "D": (41,   59),
    "E": (22,   41),
    "F": ( 0,   22),
}

# Backward compatibility alias
LOS_THRESHOLDS = PTI_LOS_THRESHOLDS

# ── Audit Thresholds (Indo-HCM 2017) ─────────────────────────────────────────
TTI_AUDIT_THRESHOLD = 1.40   # PTI > 1.4 = LOS C onset — beginning of congestion
PTI_AUDIT_THRESHOLD = 1.60   # PTI > 1.6 = LOS D — directly audit-reportable
BI_AUDIT_THRESHOLD  = 0.40   # BTI > 0.40 = poor reliability
CV_AUDIT_THRESHOLD  = 0.40   # CV > 0.40 = high variability (Table 10.7, LOS D)
FFS_AUDIT_THRESHOLD = 59.0   # %FFS < 59 = LOS D (Table 5.7, multilane divided)

# ── Value of Time ─────────────────────────────────────────────────────────────
# MORTH 2018 urban passenger car unit value-of-time (₹/hour)
VALUE_OF_TIME_INR_PER_HOUR = 109.0

# ── Posted Speed Limits (km/h) ────────────────────────────────────────────────
# Used for % Free Flow Speed calculation.
# Verify against field signage before citing in report.
POSTED_SPEED_KMPH = {
    "GS_ROAD": 50,   # Urban arterial
    "NH37":    60,   # National Highway urban section
}

# ── GCS Bucket ────────────────────────────────────────────────────────────────
GCS_BUCKET = "guwahati-mobility-audit"

# ── Local Fallback Paths ──────────────────────────────────────────────────────
CACHE_DIR  = "./cache"
EXPORT_DIR = "./audit_exports"

# ── API ───────────────────────────────────────────────────────────────────────
API_SLEEP_S = 0.12

# ── Corridor Definitions ──────────────────────────────────────────────────────
CORRIDORS = {

    "GS_ROAD": {
        "label":              "GS Road",
        "description":        "Khanapara to Jalukbari",
        "direction_inbound":  "EAST_TO_WEST",
        "direction_outbound": "WEST_TO_EAST",
        "length_km":          16.8,
        # Source: ASTC GPS geofence file (ROute_GPS.xlsx)
        # Sequence: Khanapara → Jalukbari (inbound / AM peak direction)
        "stops": [
            {"id": "GS_01", "name": "Khanapara",         "lat": 26.12019, "lng": 91.82224},
            {"id": "GS_02", "name": "Farm Gate",          "lat": 26.12574, "lng": 91.81534},
            {"id": "GS_03", "name": "Six Mile",           "lat": 26.13355, "lng": 91.80541},
            {"id": "GS_04", "name": "Rukminigaon",        "lat": 26.13552, "lng": 91.80288},
            {"id": "GS_05", "name": "Down Town",          "lat": 26.13892, "lng": 91.79861},
            {"id": "GS_06", "name": "Super Market",       "lat": 26.14192, "lng": 91.79473},
            {"id": "GS_07", "name": "Dispur",             "lat": 26.14444, "lng": 91.79167},
            {"id": "GS_08", "name": "Ganeshguri",         "lat": 26.14732, "lng": 91.78805},
            {"id": "GS_09", "name": "Walford",            "lat": 26.15283, "lng": 91.78201},
            {"id": "GS_10", "name": "Christianbasti",     "lat": 26.15607, "lng": 91.77859},
            {"id": "GS_11", "name": "Post Office",        "lat": 26.15921, "lng": 91.77502},
            {"id": "GS_12", "name": "ABC Bus Stop",       "lat": 26.16234, "lng": 91.77136},
            {"id": "GS_13", "name": "Bhangagarh",         "lat": 26.16758, "lng": 91.76564},
            {"id": "GS_14", "name": "Boraservice",        "lat": 26.16992, "lng": 91.76310},
            {"id": "GS_15", "name": "Lachitnagar",        "lat": 26.17247, "lng": 91.76055},
            {"id": "GS_16", "name": "Ulubari",            "lat": 26.17662, "lng": 91.75504},
            {"id": "GS_17", "name": "Apsara",             "lat": 26.17736, "lng": 91.75386},
            {"id": "GS_18", "name": "Paltan Bazar",       "lat": 26.17917, "lng": 91.75150},
            {"id": "GS_19", "name": "Vishal AT Road",     "lat": 26.18034, "lng": 91.74617},
            {"id": "GS_20", "name": "Laktokia",           "lat": 26.18397, "lng": 91.74647},
            {"id": "GS_21", "name": "Reserve Bank",       "lat": 26.18579, "lng": 91.74895},
            {"id": "GS_22", "name": "Gauhati High Court", "lat": 26.18789, "lng": 91.75031},
            {"id": "GS_23", "name": "Kachari",            "lat": 26.18956, "lng": 91.74733},
            {"id": "GS_24", "name": "Panbazar",           "lat": 26.18818, "lng": 91.74319},
            {"id": "GS_25", "name": "Fancybazar",         "lat": 26.18457, "lng": 91.73878},
            {"id": "GS_26", "name": "Machkhowa",          "lat": 26.17853, "lng": 91.73450},
            {"id": "GS_27", "name": "Bharalumukh",        "lat": 26.17296, "lng": 91.73029},
            {"id": "GS_28", "name": "Santipur",           "lat": 26.17045, "lng": 91.72387},
            {"id": "GS_29", "name": "Bhootnath",          "lat": 26.16928, "lng": 91.72253},
            {"id": "GS_30", "name": "Kamakhaya Gate",     "lat": 26.16549, "lng": 91.71762},
            {"id": "GS_31", "name": "Maligaon Gate-3",    "lat": 26.15975, "lng": 91.70458},
            {"id": "GS_32", "name": "Maligaon Chariali",  "lat": 26.15906, "lng": 91.69559},
            {"id": "GS_33", "name": "Adabari",            "lat": 26.15851, "lng": 91.68554},
            {"id": "GS_34", "name": "Jalukbari",          "lat": 26.15751, "lng": 91.67317},
        ],
    },

    "NH37": {
        "label":              "NH 37",
        "description":        "Khanapara to Jalukbari",
        "direction_inbound":  "EAST_TO_WEST",
        "direction_outbound": "WEST_TO_EAST",
        "length_km":          18.5,
        # Source: ASTC GPS geofence file (ROute_GPS.xlsx)
        # Tetelia/Gotanagar: landmark-referenced (Radisson Blu) — field verify
        "stops": [
            {"id": "NH_01", "name": "Khanapara",         "lat": 26.12019, "lng": 91.82224},
            {"id": "NH_02", "name": "Basistha Chariali", "lat": 26.11201, "lng": 91.79761},
            {"id": "NH_03", "name": "Games Village",     "lat": 26.11127, "lng": 91.78925},
            {"id": "NH_04", "name": "Beharbari",         "lat": 26.11102, "lng": 91.77232},
            {"id": "NH_05", "name": "Nalapara",          "lat": 26.11128, "lng": 91.76582},
            {"id": "NH_06", "name": "Sarusajai",         "lat": 26.11136, "lng": 91.75834},
            {"id": "NH_07", "name": "Lokhra",            "lat": 26.11160, "lng": 91.74927},
            {"id": "NH_08", "name": "ISBT",              "lat": 26.11493, "lng": 91.72276},
            {"id": "NH_09", "name": "Gorchuk",           "lat": 26.11572, "lng": 91.70829},
            {"id": "NH_10", "name": "Boragaon",          "lat": 26.12276, "lng": 91.68545},
            {"id": "NH_11", "name": "Tetelia/Gotanagar", "lat": 26.12850, "lng": 91.68000},
            {"id": "NH_12", "name": "Jalukbari",         "lat": 26.15520, "lng": 91.67640},
        ],
    },
}
