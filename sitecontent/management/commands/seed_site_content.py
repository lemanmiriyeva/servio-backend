"""
İctimai sayt (Ana səhifə / Funksiyalar / Qiymətlər / Haqqımızda / FAQ / Əlaqə) üçün başlanğıc
məzmunu bazaya yazır. Bunsuz bu səhifələr frontend-in öz "FALLBACK" (ehtiyat) mətni ilə
görünür (kod içində sabit), baza isə boş qalır — Baş Admin /kapitan-dan redaktə etmək
istəyəndə dəyişiklik heç bir yerə yazılmır. Bu əmr frontend-dəki hazırkı mətni EYNİ İLƏ
bazaya köçürür ki, saytın görünüşü dəyişməsin, amma artıq həqiqətən bazadan idarə olunsun.

İdempotentdir — təkrar işlədilsə, mövcud qeydləri yalnız yeniləyir (yeni surət yaratmır).
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from sitecontent.cache import invalidate_site_content_cache
from sitecontent.models import AboutValue, FaqItem, FeatureItem, HomeStep, SiteSettings
from tenants.models import Plan


class Command(BaseCommand):
    help = "İctimai saytın (Ana səhifə, Funksiyalar, Qiymətlər, Haqqımızda, FAQ, Əlaqə) başlanğıc məzmununu bazaya yazır."

    def say(self, msg, style=None):
        try:
            self.stdout.write(style(msg) if style else msg)
        except UnicodeEncodeError:
            self.stdout.write(msg.encode("ascii", "replace").decode())

    @transaction.atomic
    def handle(self, *args, **opts):
        self.seed_settings()
        self.seed_faq()
        self.seed_features()
        self.seed_about_values()
        self.seed_home_steps()
        self.seed_plans()
        invalidate_site_content_cache()
        self.say("")
        self.say("Sayt məzmunu bazaya yazıldı — /kapitan panelindən artıq redaktə edilə bilər.", self.style.SUCCESS)

    # ------------------------------------------------------------ Sayt ayarları (tək sətir)
    def seed_settings(self):
        s = SiteSettings.load()
        s.brand_name = "SERVIO"
        s.tagline = ""
        s.hero_title = "Servisinizi daha rahat idarə edin."
        s.hero_subtitle = (
            "Müştərilər, təmirlər, gəlir-xərc, anbar, borclar və hesabatlar — hamısı bir "
            "platformada. Telefon və kompüter servis bizneslər üçün ağıllı idarəetmə sistemi."
        )
        s.email = "info@servio.az"
        s.phone = "+994 50 000 00 00"
        s.whatsapp = "994500000000"
        s.address = "Bakı, Azərbaycan"
        s.hours = "Bazar ertəsi – Şənbə, 09:00 – 18:00"
        s.footer_note = ""
        s.save()
        self.say("Sayt ayarları yazıldı (brend, hero mətni, əlaqə məlumatları).")

    # ------------------------------------------------------------------------------- FAQ
    def seed_faq(self):
        items = [
            ("Servio kimlər üçündür?",
             "Telefon və kompüter təmiri ilə məşğul olan ustalar və servis mərkəzləri üçün. "
             "Müştəri, təmir, kassa, anbar, borc və hesabatların hamısı bir yerdədir."),
            ("Telefonda işləyirmi?",
             "Bəli. Sistem həm kompüter, həm də telefon ekranında rahat işləyir, ona görə də "
             "ustalar işin ortasında da məlumat daxil edə bilər."),
            ("Mənim məlumatımı başqa servis görə bilərmi?",
             "Xeyr. Hər servis ayrıca hesab kimi işləyir və yalnız öz müştərilərini, gəlirini, "
             "xərclərini, borclarını və təmir məlumatlarını görür."),
            ("Tələbəyə giriş versəm, qazancı görəcəkmi?",
             "Yox. Rol və icazələr bölməsindən şəyird üçün gəlir və net qazanc rəqəmlərini "
             "bağlaya bilərsiniz. O, təmirlərlə işləyə bilər, amma maya, qazanc və gəlir ona "
             "görünmür."),
            ("Bir neçə filialla işləmək mümkündürmü?",
             "Bəli. Basic planda 1, Pro planda 5 filial dəstəklənir. Hər plan üzrə filial və "
             "istifadəçi limiti Qiymətlər səhifəsində göstərilib."),
            ("Təchizatçıya borcu necə izləyirəm?",
             "Təmiri qeyd edəndə detalı təchizatçıdan borcla aldığınızı seçirsiniz, məbləğ "
             "təchizatçının hesabına borc kimi yazılır. Ödəyəndən sonra ödənilmiş kimi "
             "işarələyirsiniz. Detal istifadə olunmayıbsa (məsələn, plata təmiri), bu sahəni "
             "doldurmaq məcburi deyil."),
            ("Zəmanət necə hesablanır?",
             "Cihaz təhvil veriləndə zəmanət müddəti avtomatik başlayır və gün-gün geri sayılır. "
             "Müddəti bitən zəmanət “müddəti bitib” kimi göstərilir."),
            ("Pulsuz başlaya bilərəmmi?",
             "Bəli, pulsuz sınaqla başlaya bilərsiniz. Müddət və şərtlər barədə Əlaqə "
             "səhifəsindən bizə yazın."),
        ]
        for i, (q, a) in enumerate(items):
            FaqItem.objects.update_or_create(question=q, defaults={"answer": a, "order": i, "is_active": True})
        self.say(f"FAQ: {len(items)} sual-cavab yazıldı.")

    # -------------------------------------------------------------------------- Funksiyalar
    def seed_features(self):
        items = [
            ("Users", "primary", "Müştərilər", "Müştəri bazasını yaradın və asanlıqla idarə edin.",
             ["Ad, telefon və qeydlər üzrə sürətli axtarış", "Hər müştərinin bütün təmir tarixçəsi",
              "Ödənişlər, borclar və zəmanətlər bir profildə"]),
            ("Wrench", "dark", "Təmir / Xidmətlər", "Təmir prosesini izləyin, statusları qeyd edin.",
             ["Hər xidmətə avtomatik nömrə (SRV-2026-000125)",
              "Qəbul edildi → Diaqnostika → Hazırdır → Təhvil verildi",
              "Qazanc satış və maya dəyərindən avtomatik hesablanır"]),
            ("Boxes", "primary", "Anbar", "Ehtiyat hissələri və malların idarə edilməsi.",
             ["Alış və satış qiyməti, say və minimum hədd", "Stok azaldıqda xəbərdarlıq",
              "Detal istifadə olunanda say avtomatik azalır"]),
            ("Truck", "dark", "Təchizatçılar", "Təchizatçıları əlavə edin, borcları izləyin.",
             ["Alış tarixçəsi və ümumi məbləğ", "Ay sonu hesablaşma üçün borc qeydi",
              "Təmirdən avtomatik təchizatçı borcu yaratmaq"]),
            ("Wallet", "primary", "Kassa", "Gəlir və xərcləri idarə edin, kassa balansını görün.",
             ["Xidmət ödənişləri və digər gəlirlər",
              "Xərclər və təchizatçı ödənişləri balansdan çıxılır", "Bütün əməliyyatların tarixçəsi"]),
            ("BarChart3", "dark", "Hesabatlar", "Gündəlik, aylıq, illik analizlər və qrafiklər.",
             ["İstənilən tarix aralığı üzrə hesabat", "Xidmət və təchizatçı üzrə analiz",
              "Ümumi satış, maya, xərc və xalis qazanc"]),
            ("ShieldCheck", "primary", "Zəmanətlər", "Zəmanət müddətlərini izləyin, müştərilərə xəbərdarlıq edin.",
             ["Təhvildən sonra zəmanət avtomatik geri sayılır", "Bitməyə 3 gün qalanlar ayrıca görünür",
              "7 / 14 / 30 / 90 gün və ya zəmanətsiz"]),
            ("Printer", "dark", "Qəbz / Çap", "Rəsmi qəbz və təhvil-təslim sənədlərini çap edin.",
             ["A4 formatında səliqəli təhvil-təslim aktı", "Servisin öz zəmanət şərtləri mətni",
              "Müştəri və usta imza sahələri"]),
        ]
        for i, (icon, tone, title, short, points) in enumerate(items):
            FeatureItem.objects.update_or_create(
                title=title,
                defaults={
                    "icon": icon, "tone": tone, "short_description": short,
                    "points": "\n".join(points), "order": i, "is_active": True,
                },
            )
        self.say(f"Funksiyalar: {len(items)} kart yazıldı.")

    # -------------------------------------------------------------------------- Haqqımızda
    def seed_about_values(self):
        items = [
            ("Gauge", "Sadəlik",
             "Məqsəd mühasibat proqramı kimi mürəkkəb sistem yox, ustanın gündəlik işini "
             "sürətləndirən rahat alətdir. Müştəridən çapa qədər proses bir neçə klikdir."),
            ("Lock", "Məlumat təhlükəsizliyi",
             "Hər servis yalnız öz məlumatını görür. Müştəri, gəlir, xərc, təchizatçı və təmir "
             "məlumatları başqa servisə heç vaxt görünmür."),
            ("Puzzle", "Böyüməyə açıq",
             "Sistem modul əsaslıdır: filial, işçi rolları, anbar və yeni imkanlar biznesiniz "
             "böyüdükcə əlavə olunur."),
        ]
        for i, (icon, title, text) in enumerate(items):
            AboutValue.objects.update_or_create(
                title=title, defaults={"icon": icon, "text": text, "order": i, "is_active": True},
            )
        self.say(f"Haqqımızda: {len(items)} dəyər kartı yazıldı.")

    # --------------------------------------------------------------------- Necə işləyir (Ana s.)
    def seed_home_steps(self):
        items = [
            ("1", "Müştəri və cihazı qeyd edin",
             "Müştəri, cihaz, şikayət və görüləcək işi bir neçə kliklə əlavə edin."),
            ("2", "Maya, satış və təchizatçını seçin",
             "Qazanc avtomatik hesablanır, təchizatçı borcu isə lazım olarsa avtomatik yazılır."),
            ("3", "Təhvil verin və çap edin",
             "Ödənişi qeyd edin, A4 qəbz çap edin, zəmanət avtomatik geri saymağa başlasın."),
        ]
        for i, (number, title, desc) in enumerate(items):
            HomeStep.objects.update_or_create(
                title=title, defaults={"number": number, "description": desc, "order": i, "is_active": True},
            )
        self.say(f"\"Necə işləyir\": {len(items)} addım yazıldı.")

    # ---------------------------------------------------------------------------- Planlar
    def seed_plans(self):
        plans = [
            dict(name="Basic", price_monthly=19, max_branches=1, max_users=3, sort_order=1,
                 is_featured=False, show_on_pricing_page=True,
                 public_description="Tək usta və kiçik servislər üçün",
                 public_features=[
                     "Müştərilər və təmir qeydiyyatı", "Kassa, xərclər və borclar",
                     "Zəmanət izləmə və A4 qəbz", "Anbar və təchizatçılar", "Hesabatlar və analitika",
                 ]),
            dict(name="Pro", price_monthly=49, max_branches=5, max_users=15, sort_order=2,
                 is_featured=True, show_on_pricing_page=True,
                 public_description="Böyüyən və çox filiallı servislər üçün",
                 public_features=[
                     "Basic planın bütün imkanları", "5 filialadək bir hesabda",
                     "15 istifadəçiyə qədər (usta, tələbə, kassir)",
                     "Rol və icazələrin geniş idarəsi", "Böyük komanda üçün rahat nəzarət",
                 ]),
        ]
        for p in plans:
            features = p.pop("public_features")
            Plan.objects.update_or_create(
                name=p.pop("name"), defaults={**p, "public_features": "\n".join(features)},
            )
        self.say(f"Planlar: {len(plans)} plan yazıldı (Basic, Pro).")
