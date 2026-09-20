from enum import Enum


class Season(str, Enum):
    WINTER = "winter"
    SPRING = "spring"
    SUMMER = "summer"
    FALL = "fall"


class ApplicationStatus(str, Enum):
    APPLIED = "applied"
    OA = "OA"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class SearchMode(str, Enum):
    TEXT = "text"
    VECTOR = "vector"
    HYBRID = "hybrid"
