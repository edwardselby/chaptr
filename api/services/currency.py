"""
Currency rate service with lazy refresh pattern.

Provides automatic currency rate updates using a two-level throttling system:
1. In-memory throttle (60s) - prevents DB checks on every request
2. Database throttle (24h) - controls actual API calls to external service

External API: frankfurter.app (free, no API key required)
"""

import httpx
import time
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from api.repositories.global_config import GlobalConfigRepository
from api.repositories.settings import SettingsRepository

logger = logging.getLogger(__name__)

#: In-memory throttle state (module-level for persistence across requests)
_last_check_time: float = 0

#: Throttle interval - check DB at most once per minute
_IN_MEMORY_THROTTLE_SECONDS = 60

#: Normal refresh interval - update rates every 24 hours
_REFRESH_INTERVAL_HOURS = 24

#: Error backoff state (module-level)
_error_count = 0

#: Maximum backoff - cap at 1 week
_MAX_BACKOFF_HOURS = 168


def reset_throttle_state() -> None:
    """
    Reset in-memory throttle state.

    Used by tests to ensure clean state between test runs.
    """
    global _last_check_time, _error_count
    _last_check_time = 0
    _error_count = 0


class CurrencyService:
    """
    Fetch and manage currency rates with lazy refresh pattern.

    The lazy refresh pattern means:
    - Rates are NOT fetched on a schedule (no cron job)
    - Rates ARE fetched when a client triggers a sync
    - Two-level throttling prevents excessive API calls

    :Example:

    >>> # In sync endpoint
    >>> updated_rates = await CurrencyService.maybe_refresh_rates(
    ...     tenant_id=tenant_id,
    ...     base_currency="GBP",
    ...     settings_repo=SettingsRepository(db),
    ...     global_config_repo=GlobalConfigRepository(db)
    ... )
    >>> if updated_rates:
    ...     response["rates_updated"] = True
    ...     response["rates"] = updated_rates
    """

    #: External API base URL
    BASE_URL = "https://api.frankfurter.app"

    #: Request timeout in seconds
    TIMEOUT = 10.0

    @classmethod
    def should_check_refresh(cls) -> bool:
        """
        In-memory throttle check.

        Returns True if enough time has passed since last check.
        This prevents hitting the database on every sync request.

        :return: True if should check database, False if throttled
        :rtype: bool

        :Example:

        >>> if CurrencyService.should_check_refresh():
        ...     # Check database for last_refresh time
        ...     pass
        """
        global _last_check_time
        now = time.time()
        if now - _last_check_time < _IN_MEMORY_THROTTLE_SECONDS:
            return False
        _last_check_time = now
        return True

    @classmethod
    def needs_refresh(cls, last_refresh: Optional[datetime]) -> bool:
        """
        Check if rates need refreshing based on last refresh time.

        Uses exponential backoff on errors to prevent hammering
        a failing API.

        :param last_refresh: Timestamp of last successful refresh
        :type last_refresh: Optional[datetime]
        :return: True if rates should be refreshed
        :rtype: bool

        :Example:

        >>> needs = CurrencyService.needs_refresh(
        ...     datetime.utcnow() - timedelta(hours=25)
        ... )
        >>> needs
        True
        """
        if last_refresh is None:
            return True

        #: Calculate backoff interval based on error count
        global _error_count
        backoff_hours = min(
            _REFRESH_INTERVAL_HOURS * (2 ** _error_count),
            _MAX_BACKOFF_HOURS
        )

        age = datetime.utcnow() - last_refresh
        return age > timedelta(hours=backoff_hours)

    @classmethod
    async def fetch_rates(cls, base_currency: str) -> dict:
        """
        Fetch latest rates from frankfurter.app.

        The base currency is always included with rate 1.0.

        :param base_currency: Base currency code (e.g., "GBP")
        :type base_currency: str
        :return: Dictionary of currency codes to rates
        :rtype: dict
        :raises Exception: If API call fails

        :Example:

        >>> rates = await CurrencyService.fetch_rates("GBP")
        >>> rates["USD"]
        1.27
        >>> rates["GBP"]
        1.0
        """
        global _error_count

        try:
            async with httpx.AsyncClient(timeout=cls.TIMEOUT) as client:
                response = await client.get(
                    f"{cls.BASE_URL}/latest",
                    params={"base": base_currency}
                )
                response.raise_for_status()
                data = response.json()

                #: Reset error count on success
                _error_count = 0

                #: Extract rates and include base currency
                rates = data.get("rates", {})
                rates[base_currency] = 1.0

                logger.info(
                    f"Fetched {len(rates)} currency rates for base {base_currency}"
                )
                return rates

        except Exception as e:
            #: Increment error count for backoff (cap at 7 = 128x)
            _error_count = min(_error_count + 1, 7)
            logger.error(
                f"Currency fetch failed (backoff level: {_error_count}): {e}"
            )
            raise

    @classmethod
    async def maybe_refresh_rates(
        cls,
        tenant_id: UUID,
        base_currency: str,
        settings_repo: SettingsRepository,
        global_config_repo: GlobalConfigRepository
    ) -> Optional[dict]:
        """
        Lazy refresh: Check if rates need updating and fetch if so.

        This is the main entry point called from the sync endpoint.
        It implements the full two-level throttling pattern:

        1. Check in-memory throttle (skip if <60s since last check)
        2. Check database for last_refresh timestamp
        3. If stale (>24h or backoff period), fetch new rates
        4. Update tenant settings with new rates
        5. Record refresh timestamp in global_config

        :param tenant_id: Tenant to update rates for
        :type tenant_id: UUID
        :param base_currency: Base currency for rate conversion
        :type base_currency: str
        :param settings_repo: Settings repository instance
        :type settings_repo: SettingsRepository
        :param global_config_repo: Global config repository instance
        :type global_config_repo: GlobalConfigRepository
        :return: Updated rates dict if refreshed, None if skipped
        :rtype: Optional[dict]

        :Example:

        >>> rates = await CurrencyService.maybe_refresh_rates(
        ...     tenant_id=UUID("..."),
        ...     base_currency="GBP",
        ...     settings_repo=SettingsRepository(db),
        ...     global_config_repo=GlobalConfigRepository(db)
        ... )
        >>> if rates:
        ...     print(f"Updated {len(rates)} rates")
        """
        #: Level 1: In-memory throttle
        if not cls.should_check_refresh():
            logger.debug("Currency refresh: in-memory throttle active")
            return None

        #: Level 2: Check database for last refresh time
        config = await global_config_repo.get_refresh_status("currency_rates")
        last_refresh = config.get("last_refresh") if config else None

        if not cls.needs_refresh(last_refresh):
            logger.debug("Currency refresh: rates still fresh")
            return None

        #: Rates are stale - fetch new ones
        logger.info(f"Currency refresh: fetching rates for base {base_currency}")

        try:
            rates = await cls.fetch_rates(base_currency)

            #: Update tenant settings with new rates
            await settings_repo.update_rates(tenant_id, rates)

            #: Record successful refresh
            await global_config_repo.set_refresh_status("currency_rates", {
                "last_refresh": datetime.utcnow(),
                "success": True,
                "rate_count": len(rates),
                "base_currency": base_currency
            })

            logger.info(f"Currency refresh: updated {len(rates)} rates")
            return rates

        except Exception as e:
            #: Record failure for backoff tracking
            await global_config_repo.set_refresh_status("currency_rates", {
                "last_refresh": datetime.utcnow(),
                "success": False,
                "error": str(e)
            })
            logger.error(f"Currency refresh failed: {e}")
            return None
