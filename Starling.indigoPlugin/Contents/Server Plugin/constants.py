#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Starling Bridge - Plugin © Autolog 2022
#

import logging

# ============================== Custom Imports ===============================
try:
    import indigo  # noqa
except ImportError:
    pass

number = -1

debug_show_constants = False

def constant_id(constant_label) -> int:  # Auto increment constant id
    global number
    if debug_show_constants and number == -1:
        indigo.server.log("Starling Bridge Plugin internal Constant Name mapping ...", level=logging.DEBUG)
    number += 1
    if debug_show_constants:
        indigo.server.log(f"{number}: {constant_label}", level=logging.DEBUG)
    return number


# plugin Constants

try:
    # noinspection PyUnresolvedReferences
    import indigo
except ImportError:
    pass

STARLING_INTERNAL_ENCRYPTION_PASSWORD = b"Starling_AUTOLOG_47912"

ADDRESS = constant_id("ADDRESS")
ALERTS_IN_PROGRESS = constant_id("ALERTS_IN_PROGRESS")
API_COMMAND_POLL_DEVICE  = constant_id("API_COMMAND_POLL_DEVICE")
API_COMMAND_START_DEVICE  = constant_id("API_COMMAND_START_DEVICE")
API_COMMAND_STATUS = constant_id("API_COMMAND_STATUS")
API_VERSION = constant_id("API_VERSION")
CO_DEV_ID = constant_id("CO_DEV_ID")
DEVICES = constant_id("DEVICES")
EVENT = constant_id("STARLING_EVENT")
FAN_DEV_ID = constant_id("FAN_DEV_ID")
HOT_WATER_DEV_ID = constant_id("HOT_WATER_DEV_ID")
HUBS = constant_id("HUBS")
HUB_QUEUE = constant_id("STARLING_HUB_QUEUE")
HUMIDIFIER_DEV_ID = constant_id("HUMIDIFIER_DEV_ID")
INDIGO_DEVICE_TO_HUB = constant_id("INDIGO_DEVICE_TO_HUB")
INDIGO_DEVICE_TYPE_ID = constant_id("INDIGO_DEVICE_TYPE_ID")
INDIGO_DEV_ID = constant_id("INDIGO_DEV_ID")
LIST_NEST_DEVICES = constant_id("LIST_NEST_DEVICES")
LIST_NEST_DEVICES_SELECTED = constant_id("LIST_NEST_DEVICES_SELECTED")
LIST_STARLING_HUBS = constant_id("LIST_STARLING_HUBS")
MOTION_DEV_ID = constant_id("MOTION_DEV_ID")
NEST_DEVICES_BY_INDIGO_DEVICE_ID = constant_id("NEST_DEVICES_BY_INDIGO_DEVICE_ID")
NEST_DEVICES_BY_NEST_ID = constant_id("NEST_DEVICES_BY_NEST_ID")
NEST_ID = constant_id("NEST_ID")
NEST_NAME = constant_id("NEST_NAME")
NEST_WHERE = constant_id("NEST_WHERE")
PATH = constant_id("PATH")
PLUGIN_DISPLAY_NAME = constant_id("PLUGIN_DISPLAY_NAME")
PLUGIN_ID = constant_id("PLUGIN_ID")
PLUGIN_INFO = constant_id("PLUGIN_INFO")
PLUGIN_PREFS_FOLDER = constant_id("PLUGIN_PREFS_FOLDER")
PLUGIN_VERSION = constant_id("PLUGIN_VERSION")
POLLING_SECONDS = constant_id("POLLING_SECONDS")
QUEUES = constant_id("QUEUES")
REQUESTS_PREFIX = constant_id("REQUESTS_PREFIX")
REQUESTS_SUFFIX = constant_id("REQUESTS_SUFFIX")
SET_ECO_MODE = constant_id("SET_ECO_MODE")
SET_FAN = constant_id("SET_FAN")
SET_HOME_AWAY = constant_id("SET_HOME_AWAY")
SET_HOT_WATER = constant_id("SET_HOT_WATER")
SET_HUMIDIFIER = constant_id("SET_HUMIDIFIER")
SET_HUMIDIFIER_LEVEL = constant_id("SET_HUMIDIFIER_LEVEL")
SET_HVAC_MODE = constant_id("SET_HVAC_MODE")
SET_TARGET_COOLING_THRESHOLD_TEMPERATURE = constant_id("SET_TARGET_COOLING_THRESHOLD_TEMPERATURE")
SET_TARGET_HEATING_THRESHOLD_TEMPERATURE = constant_id("SET_TARGET_HEATING_THRESHOLD_TEMPERATURE")
SET_TARGET_TEMPERATURE = constant_id("SET_TARGET_TEMPERATURE")
STARLING_API_VERSION = constant_id("STARLING_API_VERSION")
STARLING_APP_NAME  = constant_id("STARLING_APP_NAME")
STARLING_DEVICE_CONNECTED = constant_id("STARLING_DEVICE_CONNECTED")
STARLING_FILTERS = constant_id("STARLING_FILTERS")
STARLING_HUBS = constant_id("STARLING_HUBS")
STOP_THREAD = constant_id("STOP_THREAD")
THREAD = constant_id("STARLING_THREAD")
THREAD_STARTED = constant_id("STARLING_THREAD_STARTED")
TRIGGERS_NEST_PROTECT = constant_id("TRIGGERS_NEST_PROTECT")
TRIGGERS_NEST_PROTECTS_ALL = constant_id("TRIGGERS_NEST_PROTECTS_ALL")


NEST_PRIMARY_INDIGO_DEVICE_TYPES_AND_NEST_PROPERTIES = dict()
NEST_PRIMARY_INDIGO_DEVICE_TYPES_AND_NEST_PROPERTIES["nestProtect"] = ["onoff"]

LOG_LEVEL_NOT_SET = 0
LOG_LEVEL_DEBUGGING = 10
LOG_LEVEL_STARLING_API = 15
LOG_LEVEL_INFO = 20
LOG_LEVEL_WARNING = 30
LOG_LEVEL_ERROR = 40
LOG_LEVEL_CRITICAL = 50

LOG_LEVEL_TRANSLATION = dict()
LOG_LEVEL_TRANSLATION[LOG_LEVEL_NOT_SET] = "Not Set"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_DEBUGGING] = "Debugging"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_STARLING_API] = "Starling API Logging"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_INFO] = "Info"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_WARNING] = "Warning"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_ERROR] = "Error"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_CRITICAL] = "Critical"

# QUEUE Priorities
QUEUE_PRIORITY_STOP_THREAD    = 0
QUEUE_PRIORITY_COMMAND_HIGH   = 100
QUEUE_PRIORITY_COMMAND_MEDIUM = 200
QUEUE_PRIORITY_POLLING        = 300
QUEUE_PRIORITY_LOW            = 400
