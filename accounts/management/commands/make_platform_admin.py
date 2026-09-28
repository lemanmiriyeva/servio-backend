from django.core.management.base import BaseCommand, CommandError
from accounts.models import User


class Command(BaseCommand):
    help = (
        "Platforma (Super Admin) hüququ verir. Mövcud istifadəçini yüksəldir və ya yenisini yaradır.\n"
        "  python manage.py make_platform_admin elvin.techfix\n"
        "  python manage.py make_platform_admin platform.admin --password parol123"
    )

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--password", help="Yeni istifadəçi yaradılırsa (və ya şifrə dəyişmək üçün)")

    def handle(self, *args, **opts):
        username, password = opts["username"], opts.get("password")
        user = User.objects.filter(username=username).first()
        if user is None:
            if not password:
                raise CommandError("İstifadəçi tapılmadı. Yeni yaratmaq üçün --password verin.")
            user = User(username=username)
            created = True
        else:
            created = False
        user.is_platform_admin = True
        if password:
            user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(
            f"{'Yaradıldı' if created else 'Yeniləndi'}: {username} — platforma admini. Giriş sonra /platform səhifəsi açıla bilər."
        ))
