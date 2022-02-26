"""Platform for light integration."""
from __future__ import annotations

import logging

import voluptuous as vol
import asyncio

# Import the device class from the component that you want to support
import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    PLATFORM_SCHEMA,
    LightEntity,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR_TEMP,
    SUPPORT_COLOR)
from homeassistant.const import (
    CONF_NAME,
    CONF_HOST,
    CONF_TOKEN,
    ATTR_ENTITY_ID
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from miio import Device, DeviceException
from math import ceil

DOMAIN = "xiaomi_miio_opple_light"
DATA_KEY = 'light.xiaomi_miio_opple_light'

CONF_MIN_BRIGHTNESS = 'min_brightness'
CONF_MAX_BRIGHTNESS = 'max_brightness'
CONF_MIN_MIREDS = 'min_mireds'
CONF_MAX_MIREDS = 'max_mireds'

DEFAULT_SUPPORTED_FEATURES = SUPPORT_BRIGHTNESS | SUPPORT_COLOR_TEMP

_LOGGER = logging.getLogger(__name__)

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_TOKEN): cv.string,
    vol.Optional(CONF_MIN_BRIGHTNESS, default=7): cv.positive_int,
    vol.Optional(CONF_MAX_BRIGHTNESS, default=100): cv.positive_int,
    vol.Optional(CONF_MIN_MIREDS, default=3000): cv.positive_int,
    vol.Optional(CONF_MAX_MIREDS, default=5700): cv.positive_int
})

def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}

    name = config.get(CONF_NAME)
    host = config.get(CONF_HOST)
    token = config.get(CONF_TOKEN)
    
    min_brightness = config.get(CONF_MIN_BRIGHTNESS)
    max_brightness = config.get(CONF_MAX_BRIGHTNESS)
    min_mireds = config.get(CONF_MIN_MIREDS)
    max_mireds = config.get(CONF_MAX_MIREDS)
    
    hub = OppleLight(name, host, token, min_brightness, max_brightness, min_mireds, max_mireds)
    hass.data[DATA_KEY][host] = hub
    add_entities([hub], update_before_add=True)
    

class OppleLight(LightEntity):

    def __init__(
        self, 
        name: str, 
        host: str, 
        token: str, 
        min_brightness: int, 
        max_brightness: int, 
        min_mireds: int, 
        max_mireds: int
    ) -> None:
        self._name = name
        self._device = Device(host, token)
        
        self._state = None
        self._brightness = None
        self._color_temp = None
        
        self._min_brightness = min_brightness
        self._max_brightness = max_brightness
        self._min_mireds = min_mireds
        self._max_mireds = max_mireds
        
        device_info = self._device.info()
        self._unique_id = "{}-{}".format(device_info.model, device_info.mac_address)

    async def async_update(self) -> None:
        try:
            BaseInfo = self._device.raw_command('SyncBaseInfo', [])
            self._state = BaseInfo[0]
            self._brightness = BaseInfo[2]
            self._color_temp = BaseInfo[1]
        except Exception:
            _LOGGER.error('Update state error.', exc_info=True)
            
    async def change_state(self, method: str, params: tuple) -> bool:
        try:
            res = self._device.raw_command(method, params)
            if (res[0] != 'ok'):
                _LOGGER.error('Change_state failed for %s: %s', method, ' '.join(params))
                return True
            else:
                return False
        except Exception:
            _LOGGER.error('Change_state error.', exc_info=True)
            
    async def async_turn_on(self, **kwargs: Any) -> None:
        if not self._state:
            result = await self.change_state("SetState", [True])
            if result:
                self._state = True
        
        if self.supported_features & SUPPORT_BRIGHTNESS and ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            percent_brightness = ceil( (brightness - 1)*(self._max_brightness - self._min_brightness)/(255-1)+self._min_brightness )
            _LOGGER.debug('Setting brightness: %s %s%%', brightness, percent_brightness)
            result = await self.change_state('SetBrightness', [percent_brightness])
            if result:
                self._brightness = brightness
                
        if self.supported_features & SUPPORT_COLOR_TEMP and ATTR_COLOR_TEMP in kwargs:
            mired = kwargs[ATTR_COLOR_TEMP]
            color_temp = mired
            _LOGGER.debug('Setting color temperature: %s mireds, %s ct', mired, color_temp)
            result = await self.change_state('SetColorTemperature', [color_temp])
            if result:
                self._color_temp = color_temp
                
    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._state:
            result = await self.change_state("SetState", [False])
            if result:
                self._state = False

    @property
    def name(self) -> str:
        """Return the display name of this light."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return an unique ID."""
        return self._unique_id
        
    @property
    def supported_features(self) -> int:
        return DEFAULT_SUPPORTED_FEATURES

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self._state

    @property
    def brightness(self) -> int:
        return ceil( (self._brightness - self._min_brightness)*(255-1)/(self._max_brightness - self._min_brightness)+1 )

    @property
    def color_temp(self) -> int:
        return self._color_temp
        
    @property
    def min_mireds(self) -> int:
        return self._min_mireds

    @property
    def max_mireds(self) -> int:
        return self._max_mireds
