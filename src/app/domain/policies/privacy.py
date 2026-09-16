import uuid

from app.domain.aggregates.settings import UserSettings
from app.domain.value_objects.privacy import PrivacyScope


class ProfilePrivacyPolicy:
    """
    Доменная политика видимости и приватности данных профиля пользователя.
    Инкапсулирует бизнес-правила доступа к био, аватару и видимости в поиске.
    """

    @staticmethod
    def can_view_bio(
        target_user_id: uuid.UUID,
        settings: UserSettings,
        viewer_id: uuid.UUID | None = None,
    ) -> bool:
        """
        Проверяет, разрешено ли зрителю viewer_id видеть био целевого пользователя target_user_id.
        Владелец всегда видит своё био; сторонние пользователи видят био, если scope == ALL.
        """
        if viewer_id is not None and viewer_id == target_user_id:
            return True
        return settings.privacy.who_can_see_bio == PrivacyScope.ALL

    @staticmethod
    def can_view_avatar(
        target_user_id: uuid.UUID,
        settings: UserSettings,
        viewer_id: uuid.UUID | None = None,
    ) -> bool:
        """
        Проверяет, разрешено ли зрителю viewer_id видеть аватар целевого пользователя target_user_id.
        Владелец всегда видит свой аватар; сторонние пользователи видят аватар, если scope == ALL.
        """
        if viewer_id is not None and viewer_id == target_user_id:
            return True
        return settings.privacy.who_can_see_avatar == PrivacyScope.ALL

    @staticmethod
    def can_find_by_username(
        target_user_id: uuid.UUID,
        settings: UserSettings,
        viewer_id: uuid.UUID | None = None,
    ) -> bool:
        """
        Проверяет, разрешено ли находить профиль в поиске по username.
        Владелец всегда может найти свой профиль; сторонние пользователи — если scope == ALL.
        """
        if viewer_id is not None and viewer_id == target_user_id:
            return True
        return settings.privacy.who_can_find_by_username == PrivacyScope.ALL
