from typing import Optional
from uuid import UUID
from datetime import datetime, timezone
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import structlog

from app.database.models import (
    Notification, NotificationPreference, User, Business
)

logger = structlog.get_logger(__name__)


@dataclass
class NotificationPayload:
    title: str
    body: str
    notification_type: str
    priority: str
    action_url: Optional[str] = None
    action_data: Optional[dict] = None
    metadata: Optional[dict] = None


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def send_notification(
        self,
        user_id: UUID,
        business_id: UUID,
        payload: NotificationPayload,
        channels: list[str] = None,
    ) -> list[Notification]:
        if channels is None:
            channels = ["in_app"]

        preference = await self._get_preference(user_id, business_id)
        
        if self._is_in_quiet_hours(preference):
            logger.info("notification_skipped_quiet_hours", user_id=str(user_id))
            return []

        notifications = []
        
        for channel in channels:
            if channel == "in_app" and (not preference or preference.in_app_enabled):
                notif = await self._create_notification(
                    user_id, business_id, payload, "in_app"
                )
                notifications.append(notif)
            
            elif channel == "email" and preference and preference.email_enabled:
                notif = await self._create_notification(
                    user_id, business_id, payload, "email"
                )
                notifications.append(notif)
                await self._queue_email(preference.email_address, payload)
            
            elif channel == "whatsapp" and preference and preference.whatsapp_enabled:
                if await self._check_whatsapp_limit(preference):
                    notif = await self._create_notification(
                        user_id, business_id, payload, "whatsapp"
                    )
                    notifications.append(notif)
                    await self._queue_whatsapp(preference.whatsapp_number, payload)
            
            elif channel == "sms" and preference and preference.sms_enabled:
                if await self._check_sms_limit(preference):
                    notif = await self._create_notification(
                        user_id, business_id, payload, "sms"
                    )
                    notifications.append(notif)
                    await self._queue_sms(preference.sms_number, payload)

        logger.info(
            "notifications_sent",
            user_id=str(user_id),
            business_id=str(business_id),
            count=len(notifications),
            channels=channels,
        )

        return notifications

    async def send_critical_stock_alert(
        self,
        business_id: UUID,
        item_name: str,
        current_stock: float,
        days_until_stockout: int,
    ) -> list[Notification]:
        business = await self.db.get(Business, business_id)
        if not business:
            return []

        user = await self.db.get(User, business.owner_id)
        if not user:
            return []

        payload = NotificationPayload(
            title=f"🚨 Critical: {item_name} Stock Low",
            body=f"Only {current_stock:.0f} units left. Stock will run out in ~{days_until_stockout} day(s).",
            notification_type="critical_stock",
            priority="critical",
            action_url=f"/inventory?item={item_name}",
            action_data={
                "alert_type": "critical_stock",
                "item_name": item_name,
                "current_stock": current_stock,
                "days_until_stockout": days_until_stockout,
            },
        )

        return await self.send_notification(
            user.id,
            business_id,
            payload,
            channels=["whatsapp", "in_app"],
        )

    async def send_pricing_opportunity(
        self,
        business_id: UUID,
        item_name: str,
        opportunity: str,
        expected_impact: str,
    ) -> list[Notification]:
        business = await self.db.get(Business, business_id)
        if not business:
            return []

        user = await self.db.get(User, business.owner_id)
        if not user:
            return []

        payload = NotificationPayload(
            title=f"💰 Pricing Opportunity: {item_name}",
            body=f"{opportunity}\n\nExpected impact: {expected_impact}",
            notification_type="pricing_opportunity",
            priority="medium",
            action_url=f"/pricing?item={item_name}",
            action_data={
                "alert_type": "pricing_opportunity",
                "item_name": item_name,
            },
        )

        return await self.send_notification(
            user.id,
            business_id,
            payload,
            channels=["in_app", "email"],
        )

    async def get_user_notifications(
        self,
        user_id: UUID,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        query = select(Notification).where(Notification.user_id == user_id)
        
        if unread_only:
            query = query.where(Notification.read_at == None)
        
        query = query.order_by(Notification.created_at.desc()).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def mark_as_read(self, notification_id: UUID, user_id: UUID) -> bool:
        notification = await self.db.get(Notification, notification_id)
        
        if not notification or notification.user_id != user_id:
            return False
        
        notification.read_at = datetime.now(timezone.utc)
        notification.status = "read"
        await self.db.commit()
        
        return True

    async def mark_all_as_read(self, user_id: UUID) -> int:
        result = await self.db.execute(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.read_at == None
            )
        )
        notifications = result.scalars().all()
        
        for notif in notifications:
            notif.read_at = datetime.now(timezone.utc)
            notif.status = "read"
        
        await self.db.commit()
        
        return len(notifications)

    async def update_preferences(
        self,
        user_id: UUID,
        business_id: UUID,
        preferences: dict,
    ) -> NotificationPreference:
        preference = await self._get_preference(user_id, business_id)
        
        if not preference:
            preference = NotificationPreference(
                user_id=user_id,
                business_id=business_id,
            )
            self.db.add(preference)
        
        for key, value in preferences.items():
            if hasattr(preference, key):
                setattr(preference, key, value)
        
        await self.db.commit()
        await self.db.refresh(preference)
        
        return preference

    async def _get_preference(
        self,
        user_id: UUID,
        business_id: UUID,
    ) -> Optional[NotificationPreference]:
        result = await self.db.execute(
            select(NotificationPreference).where(
                and_(
                    NotificationPreference.user_id == user_id,
                    NotificationPreference.business_id == business_id,
                )
            )
        )
        return result.scalar_one_or_none()

    def _is_in_quiet_hours(self, preference: Optional[NotificationPreference]) -> bool:
        if not preference or not preference.quiet_hours_enabled:
            return False
        
        now = datetime.now(timezone.utc).time()
        start = preference.quiet_hours_start
        end = preference.quiet_hours_end
        
        if start <= end:
            return start <= now <= end
        else:
            return now >= start or now <= end

    async def _check_whatsapp_limit(self, preference: NotificationPreference) -> bool:
        today = datetime.now(timezone.utc).date()
        
        result = await self.db.execute(
            select(
                select(Notification)
                .where(
                    Notification.user_id == preference.user_id,
                    Notification.channel == "whatsapp",
                    Notification.created_at >= today,
                )
                .count()
            )
        )
        count = result.scalar()
        
        return count < preference.max_whatsapp_per_day

    async def _check_sms_limit(self, preference: NotificationPreference) -> bool:
        today = datetime.now(timezone.utc).date()
        
        result = await self.db.execute(
            select(
                select(Notification)
                .where(
                    Notification.user_id == preference.user_id,
                    Notification.channel == "sms",
                    Notification.created_at >= today,
                )
                .count()
            )
        )
        count = result.scalar()
        
        return count < preference.max_sms_per_day

    async def _create_notification(
        self,
        user_id: UUID,
        business_id: UUID,
        payload: NotificationPayload,
        channel: str,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            business_id=business_id,
            title=payload.title,
            body=payload.body,
            notification_type=payload.notification_type,
            priority=payload.priority,
            channel=channel,
            status="pending",
            action_url=payload.action_url,
            action_data=payload.action_data,
            metadata=payload.metadata or {},
        )
        
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)
        
        return notification

    async def _queue_email(self, email: str, payload: NotificationPayload) -> None:
        logger.info("email_queued", to=email, subject=payload.title)

    async def _queue_whatsapp(self, phone: str, payload: NotificationPayload) -> None:
        logger.info("whatsapp_queued", to=phone, body=payload.body)

    async def _queue_sms(self, phone: str, payload: NotificationPayload) -> None:
        logger.info("sms_queued", to=phone, body=payload.body[:160])
