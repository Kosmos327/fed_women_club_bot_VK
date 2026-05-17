from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WebPartnerCategory:
    label: str
    slug: str | None


# WEB catalog accepts category_slug values. There is no categories endpoint in this
# VK bot repo, so keep the known fallback mapping explicit and centralized.
WEB_PARTNER_CATEGORIES: tuple[WebPartnerCategory, ...] = (
    WebPartnerCategory("Красота", "beauty"),
    WebPartnerCategory("Маникюр / педикюр", "nails"),
    WebPartnerCategory("Волосы / окрашивание", "hair"),
    WebPartnerCategory("Брови / ресницы", "brows-lashes"),
    WebPartnerCategory("Косметология", "cosmetology"),
    WebPartnerCategory("Массаж / SPA", "massage-spa"),
    WebPartnerCategory("Фитнес / йога", "fitness-yoga"),
    WebPartnerCategory("Здоровье", "health"),
    WebPartnerCategory("Психология", "psychology"),
    WebPartnerCategory("Одежда / аксессуары", "clothes-accessories"),
    WebPartnerCategory("Кафе / рестораны", "cafes-restaurants"),
    WebPartnerCategory("Обучение / мастер-классы", "education-workshops"),
    WebPartnerCategory("Фотосессии", "photo"),
    WebPartnerCategory("Цветы / подарки", "flowers-gifts"),
    WebPartnerCategory("Другое", "other"),
)

WEB_PARTNER_CATEGORY_LABEL_TO_SLUG = {category.label: category.slug for category in WEB_PARTNER_CATEGORIES}
WEB_PARTNER_CATEGORY_SLUG_TO_LABEL = {category.slug: category.label for category in WEB_PARTNER_CATEGORIES if category.slug}


def get_web_partner_category_slug(label: str | None) -> str | None:
    if not label:
        return None
    return WEB_PARTNER_CATEGORY_LABEL_TO_SLUG.get(label)


def get_web_partner_category_label(slug: str | None, fallback: str | None = None) -> str | None:
    if not slug:
        return fallback
    return WEB_PARTNER_CATEGORY_SLUG_TO_LABEL.get(slug, fallback or slug)
