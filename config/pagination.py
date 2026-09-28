from rest_framework.pagination import PageNumberPagination


class FlexiblePageNumberPagination(PageNumberPagination):
    """Frontend `?page_size=100` göndərir; əvvəl bu parametr nəzərə alınmırdı (hamısı 20-də qalırdı)."""
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 1000
