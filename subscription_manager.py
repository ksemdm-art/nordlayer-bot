"""
Subscription manager for handling user notification preferences.
"""
import logging
from typing import Dict, Set, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import os

logger = logging.getLogger(__name__)


@dataclass
class UserSubscription:
    """User subscription data"""
    user_id: int
    email: str
    subscribed_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True
    notification_types: Set[str] = field(default_factory=lambda: {"status_change", "order_ready"})


class SubscriptionManager:
    """Manages user subscriptions for notifications"""
    
    def __init__(self, storage_file: str = "user_subscriptions.json"):
        self.storage_file = storage_file
        self.subscriptions: Dict[int, UserSubscription] = {}
        self._load_subscriptions()
    
    def _load_subscriptions(self):
        """Load subscriptions from storage file"""
        if not os.path.exists(self.storage_file):
            logger.info("No subscription file found, starting with empty subscriptions")
            return
        
        try:
            with open(self.storage_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for user_id_str, sub_data in data.items():
                user_id = int(user_id_str)
                subscription = UserSubscription(
                    user_id=user_id,
                    email=sub_data['email'],
                    subscribed_at=datetime.fromisoformat(sub_data['subscribed_at']),
                    is_active=sub_data.get('is_active', True),
                    notification_types=set(sub_data.get('notification_types', ["status_change", "order_ready"]))
                )
                self.subscriptions[user_id] = subscription
            
            logger.info(f"Loaded {len(self.subscriptions)} subscriptions")
            
        except Exception as e:
            logger.error(f"Error loading subscriptions: {e}")
            self.subscriptions = {}
    
    def _save_subscriptions(self):
        """Save subscriptions to storage file"""
        try:
            data = {}
            for user_id, subscription in self.subscriptions.items():
                data[str(user_id)] = {
                    'email': subscription.email,
                    'subscribed_at': subscription.subscribed_at.isoformat(),
                    'is_active': subscription.is_active,
                    'notification_types': list(subscription.notification_types)
                }
            
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Saved {len(self.subscriptions)} subscriptions")
            
        except Exception as e:
            logger.error(f"Error saving subscriptions: {e}")
    
    def subscribe_user(self, user_id: int, email: str, notification_types: Optional[Set[str]] = None) -> bool:
        """
        Subscribe user to notifications
        
        Args:
            user_id: Telegram user ID
            email: User's email address
            notification_types: Types of notifications to subscribe to
            
        Returns:
            True if subscription was successful
        """
        try:
            if notification_types is None:
                notification_types = {"status_change", "order_ready"}
            
            subscription = UserSubscription(
                user_id=user_id,
                email=email,
                notification_types=notification_types
            )
            
            self.subscriptions[user_id] = subscription
            self._save_subscriptions()
            
            logger.info(f"User {user_id} subscribed to notifications for email {email}")
            return True
            
        except Exception as e:
            logger.error(f"Error subscribing user {user_id}: {e}")
            return False
    
    def unsubscribe_user(self, user_id: int) -> bool:
        """
        Unsubscribe user from notifications
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if unsubscription was successful
        """
        try:
            if user_id in self.subscriptions:
                self.subscriptions[user_id].is_active = False
                self._save_subscriptions()
                logger.info(f"User {user_id} unsubscribed from notifications")
                return True
            else:
                logger.warning(f"User {user_id} not found in subscriptions")
                return False
                
        except Exception as e:
            logger.error(f"Error unsubscribing user {user_id}: {e}")
            return False
    
    def resubscribe_user(self, user_id: int) -> bool:
        """
        Resubscribe user to notifications
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if resubscription was successful
        """
        try:
            if user_id in self.subscriptions:
                self.subscriptions[user_id].is_active = True
                self._save_subscriptions()
                logger.info(f"User {user_id} resubscribed to notifications")
                return True
            else:
                logger.warning(f"User {user_id} not found in subscriptions")
                return False
                
        except Exception as e:
            logger.error(f"Error resubscribing user {user_id}: {e}")
            return False
    
    def is_subscribed(self, user_id: int, notification_type: str = "status_change") -> bool:
        """
        Check if user is subscribed to a specific notification type
        
        Args:
            user_id: Telegram user ID
            notification_type: Type of notification to check
            
        Returns:
            True if user is subscribed and active
        """
        subscription = self.subscriptions.get(user_id)
        if not subscription or not subscription.is_active:
            return False
        
        return notification_type in subscription.notification_types
    
    def get_subscription(self, user_id: int) -> Optional[UserSubscription]:
        """
        Get user subscription data
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            UserSubscription object or None if not found
        """
        return self.subscriptions.get(user_id)
    
    def get_subscribed_users_by_email(self, email: str) -> List[int]:
        """
        Get all user IDs subscribed to notifications for a specific email
        
        Args:
            email: Email address to search for
            
        Returns:
            List of user IDs
        """
        user_ids = []
        for user_id, subscription in self.subscriptions.items():
            if (subscription.email.lower() == email.lower() and 
                subscription.is_active):
                user_ids.append(user_id)
        
        return user_ids
    
    def update_notification_types(self, user_id: int, notification_types: Set[str]) -> bool:
        """
        Update user's notification type preferences
        
        Args:
            user_id: Telegram user ID
            notification_types: New set of notification types
            
        Returns:
            True if update was successful
        """
        try:
            if user_id in self.subscriptions:
                self.subscriptions[user_id].notification_types = notification_types
                self._save_subscriptions()
                logger.info(f"Updated notification types for user {user_id}: {notification_types}")
                return True
            else:
                logger.warning(f"User {user_id} not found in subscriptions")
                return False
                
        except Exception as e:
            logger.error(f"Error updating notification types for user {user_id}: {e}")
            return False
    
    def cleanup_old_subscriptions(self, days: int = 365) -> int:
        """
        Clean up old inactive subscriptions
        
        Args:
            days: Number of days after which to remove inactive subscriptions
            
        Returns:
            Number of subscriptions removed
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            removed_count = 0
            
            user_ids_to_remove = []
            for user_id, subscription in self.subscriptions.items():
                if (not subscription.is_active and 
                    subscription.subscribed_at < cutoff_date):
                    user_ids_to_remove.append(user_id)
            
            for user_id in user_ids_to_remove:
                del self.subscriptions[user_id]
                removed_count += 1
            
            if removed_count > 0:
                self._save_subscriptions()
                logger.info(f"Cleaned up {removed_count} old subscriptions")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error cleaning up subscriptions: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get subscription statistics
        
        Returns:
            Dictionary with subscription stats
        """
        total = len(self.subscriptions)
        active = sum(1 for sub in self.subscriptions.values() if sub.is_active)
        inactive = total - active
        
        return {
            "total": total,
            "active": active,
            "inactive": inactive
        }