from app.application.queries.base import BaseQuery, BaseQueryResult, BaseResponse
from app.application.queries.profiles import (
    CheckProfileExistsQuery,
    GetBatchProfilesQuery,
    GetMyProfileQuery,
    GetPublicProfileQuery,
    MyProfileResult,
    ProfileDTO,
    PublicProfileDTO,
    PublicProfileResult,
    SearchByUsernameQuery,
)
from app.application.queries.settings import (
    GetMySettingsQuery,
    MySettingsResult,
    SettingsDTO,
)

__all__ = [
    "BaseQuery",
    "BaseQueryResult",
    "BaseResponse",
    "CheckProfileExistsQuery",
    "GetBatchProfilesQuery",
    "GetMyProfileQuery",
    "GetMySettingsQuery",
    "GetPublicProfileQuery",
    "MyProfileResult",
    "MySettingsResult",
    "ProfileDTO",
    "PublicProfileDTO",
    "PublicProfileResult",
    "SearchByUsernameQuery",
    "SettingsDTO",
]
