from decimal import Decimal
from rest_framework import serializers
from customers.models import Customer
from customers.serializers import CustomerSerializer
from suppliers.models import SupplierPurchase, PurchaseStatus
from .models import (
    RepairOrder, RepairPayment, RepairStatus, RepairStatusHistory, RepairWarrantyReturn, SupplierReturnStatus,
)


class RepairPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepairPayment
        fields = ["id", "amount", "method", "paid_at"]
        read_only_fields = ["id", "paid_at"]


class RepairOrderListSerializer(serializers.ModelSerializer):
    """Siyahı/dashboard üçün yüngül forma."""
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    customer_initials = serializers.CharField(source="customer.initials", read_only=True)
    warranty_days_left = serializers.ReadOnlyField()
    remaining_debt = serializers.ReadOnlyField()
    last_status_at = serializers.ReadOnlyField()

    class Meta:
        model = RepairOrder
        fields = [
            "id", "number", "customer", "customer_name", "customer_initials",
            "device_brand", "device_model", "issue_description",
            "status", "payment_status", "sale_price", "remaining_debt",
            "warranty_days_left", "received_at", "delivered_at", "last_status_at",
        ]


class RepairWarrantyReturnSerializer(serializers.ModelSerializer):
    repair_number = serializers.CharField(source="repair.number", read_only=True)
    customer_name = serializers.CharField(source="repair.customer.full_name", read_only=True)
    supplier_id = serializers.SerializerMethodField()
    supplier_name = serializers.SerializerMethodField()
    part_description = serializers.SerializerMethodField()

    class Meta:
        model = RepairWarrantyReturn
        fields = [
            "id", "repair", "repair_number", "customer_name", "reason",
            "refund_amount", "supplier_purchase", "supplier_id", "supplier_name",
            "part_description", "return_amount", "supplier_status", "supplier_note",
            "supplier_resolved_at", "created_at",
        ]
        read_only_fields = fields

    def get_supplier_id(self, obj):
        return obj.supplier_purchase.supplier_id if obj.supplier_purchase_id else None

    def get_supplier_name(self, obj):
        return obj.supplier_purchase.supplier.name if obj.supplier_purchase_id else None

    def get_part_description(self, obj):
        return obj.supplier_purchase.description if obj.supplier_purchase_id else None


class WarrantyReturnCreateSerializer(serializers.Serializer):
    reason = serializers.CharField()
    refund_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)
    supplier_purchase_id = serializers.PrimaryKeyRelatedField(
        source="supplier_purchase", queryset=SupplierPurchase.objects.all(), required=False, allow_null=True
    )
    return_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)
    send_to_supplier = serializers.BooleanField(required=False, default=True)

    def validate_supplier_purchase(self, sp):
        request = self.context["request"]
        if sp is not None and sp.shop_id != request.user.shop_id:
            raise serializers.ValidationError("Bu alış sizin mağazaya aid deyil.")
        return sp

    def save(self, **kwargs):
        request = self.context["request"]
        repair: RepairOrder = self.context["repair"]
        data = self.validated_data
        supplier_purchase = data.get("supplier_purchase")
        return_amount = data.get("return_amount") or (supplier_purchase.amount if supplier_purchase else 0)

        wr = RepairWarrantyReturn.objects.create(
            shop=repair.shop, repair=repair,
            reason=data["reason"],
            refund_amount=data.get("refund_amount") or 0,
            supplier_purchase=supplier_purchase,
            return_amount=return_amount,
            created_by=request.user,
        )
        if wr.refund_amount and wr.refund_amount > 0:
            from finance.models import CashTransaction, TransactionType
            CashTransaction.objects.create(
                shop=repair.shop, branch=repair.branch, type=TransactionType.REFUND,
                amount=wr.refund_amount, method="cash",
                description=f"{repair.number}, {repair.customer.full_name} — zəmanət qaytarması",
                repair=repair, created_by=request.user,
            )
        if data.get("send_to_supplier", True) and wr.supplier_purchase_id:
            wr.send_to_supplier()
        return wr


class SupplierReturnDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=[SupplierReturnStatus.ACCEPTED, SupplierReturnStatus.REJECTED])
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def save(self, **kwargs):
        wr: RepairWarrantyReturn = self.context["warranty_return"]
        wr.resolve_supplier(self.validated_data["decision"], self.validated_data.get("note", ""))
        return wr


class RepairStatusHistorySerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = RepairStatusHistory
        fields = ["status", "status_display", "changed_at"]


class RepairOrderDetailSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)
    customer_id = serializers.PrimaryKeyRelatedField(
        source="customer", queryset=Customer.objects.all(), write_only=True
    )
    payments = RepairPaymentSerializer(many=True, read_only=True)
    supplier_purchases = serializers.SerializerMethodField()
    warranty_returns = RepairWarrantyReturnSerializer(many=True, read_only=True)
    status_history = RepairStatusHistorySerializer(many=True, read_only=True)
    paid_amount = serializers.ReadOnlyField()
    remaining_debt = serializers.ReadOnlyField()
    profit = serializers.ReadOnlyField()
    warranty_end_date = serializers.ReadOnlyField()
    warranty_days_left = serializers.ReadOnlyField()

    # DİQQƏT: bunlar RepairOrder-in öz sahələri DEYİL — "Yeni xidmət" formasının "Detal
    # mənbəyi" (təchizatçıdan borc / nağd alındı) və "İlkin ödəniş" addımlarını YARADILMA
    # ANINDA, təmirlə BİR YERD�ə, eyni DB tranzaksiyası daxilində yerinə yetirmək üçün əlavə
    # ediliblər (bax: create() aşağıda). Əvvəllər bunlar ayrı-ayrı HTTP sorğuları (əvvəlcə
    # təmir yaradılır, SONRA ayrıca supplier-purchase/payment sorğusu göndərilirdi) idi —
    # nəticədə kassada pul olmadığı üçün ikinci addım rədd edilsə belə, təmirin özü artıq
    # yaradılmış və DB-də qalmış olurdu ("error göstərir, amma yenə də yaradır"). İndi hamısı
    # tək bir atomic() bloku daxilindədir: balans yoxlanışı uğursuz olarsa, TƏMİR DƏ DAXİL
    # OLMAQLA heç nə yaradılmır.
    part_mode = serializers.ChoiceField(
        choices=["none", "credit", "cash"], required=False, default="none", write_only=True
    )
    part_supplier_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    part_description = serializers.CharField(required=False, allow_blank=True, write_only=True)
    # DİQQƏT: "Nağd aldım — borcsuz" seçiləndə əvvəllər ödəniş üsulu HƏMİŞƏ "cash" idi —
    # kartla ödəsə belə kassa balansı (nağd) yoxlanırdı, kart balansında kifayət qədər pul
    # olsa belə "Kassada vəsait yoxdur" xətası verirdi. İndi bu, ayrıca seçilə bilir.
    part_payment_method = serializers.ChoiceField(
        choices=["cash", "card", "bank_transfer"], required=False, default="cash", write_only=True
    )
    initial_payment_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True, write_only=True
    )
    initial_payment_method = serializers.ChoiceField(
        choices=["cash", "card", "bank_transfer"], required=False, default="cash", write_only=True
    )

    class Meta:
        model = RepairOrder
        fields = [
            "id", "number", "customer", "customer_id",
            "device_brand", "device_model", "device_imei", "device_serial", "accessories_note",
            "technician_name",
            "issue_description", "work_done_note",
            "cost_price", "sale_price", "profit",
            "status", "payment_status", "debt_due_date",
            "warranty_days", "warranty_started_at", "warranty_end_date", "warranty_days_left",
            "received_at", "delivered_at",
            "payments", "supplier_purchases", "warranty_returns", "status_history",
            "paid_amount", "remaining_debt",
            "created_at",
            "part_mode", "part_supplier_id", "part_description", "part_payment_method",
            "initial_payment_amount", "initial_payment_method",
        ]
        read_only_fields = ["id", "number", "created_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not user.has_module_permission("revenue_numbers"):
            # Maya və qazanc — 'Gəlir / net mənfəət rəqəmləri' icazəsi olmayan rola görünmür
            data["cost_price"] = None
            data["profit"] = None
            data["supplier_purchases"] = []
            for wr in data.get("warranty_returns", []):
                wr["return_amount"] = None
        return data

    def get_supplier_purchases(self, obj):
        return [
            {"id": p.id, "supplier": p.supplier.name, "description": p.description,
             "amount": p.amount, "paid_amount": p.paid_amount,
             # Ləğv edilmiş alış üçün "qalıq borc" artıq göstərilmir (0) — təmir ləğv
             # ediləndə bu alış da ləğv olunur və ümumi təchizatçı borcundan çıxır
             # (bax Supplier.total_debt), ona görə burda da borc kimi görünməməlidir.
             "remaining": 0 if p.status == PurchaseStatus.CANCELLED else p.remaining,
             "status": p.status, "status_display": p.get_status_display()}
            for p in obj.supplier_purchases.select_related("supplier").all()
        ]

    def create(self, validated_data):
        from django.db import transaction
        from rest_framework.exceptions import ValidationError

        request = self.context["request"]
        # Bunlar model sahəsi deyil — DB-yə birbaşa yazılmazdan əvvəl çıxarılır.
        part_mode = validated_data.pop("part_mode", "none")
        part_supplier_id = validated_data.pop("part_supplier_id", None)
        part_description = validated_data.pop("part_description", "")
        part_payment_method = validated_data.pop("part_payment_method", "cash")
        initial_payment_amount = validated_data.pop("initial_payment_amount", None)
        initial_payment_method = validated_data.pop("initial_payment_method", "cash")

        validated_data["shop"] = request.user.shop
        validated_data["branch"] = request.user.branch
        validated_data["created_by"] = request.user

        # DİQQƏT (əsas düzəliş): bütün bu addımlar BİR tranzaksiya daxilindədir. Əvvəllər
        # təmir əvvəlcə yaradılıb commit olunur, SONRA detal/ödəniş üçün ayrıca sorğular
        # göndərilirdi — kassada pul olmadığı üçün o sonrakı addım rədd edilsə belə, təmirin
        # özü artıq DB-də qalmış olurdu. İndi assert_sufficient_balance HƏR hansı addımda
        # ValidationError qaldırarsa, bu bloku əhatə edən atomic() TƏMİR DƏ DAXİL OLMAQLA
        # hər şeyi geri alır (rollback) — heç nə yaradılmır.
        with transaction.atomic():
            repair = super().create(validated_data)

            # Cihaz xarici ustaya göndərilibsə (technician_name doldurulub) və ustaya verilən
            # məbləğ (cost_price) qeyd olunubsa — bu, təchizatçı siyahısından seçilən bir
            # "Supplier" deyil, sadəcə ad yazılan xarici usta olduğu üçün heç vaxt Kassadan
            # məxaric kimi düşmürdü (yalnız profit = sale_price - cost_price hesablamasında
            # görünürdü, real pul Kassada "qalırdı" kimi göstərilirdi). İndi bu məbləği birbaşa
            # Kassadan xərc kimi yazırıq ki, balans da real vəziyyəti göstərsin.
            if repair.technician_name and repair.cost_price and repair.cost_price > 0:
                from finance.models import CashTransaction, TransactionType, assert_sufficient_balance
                assert_sufficient_balance(repair.shop, repair.cost_price, "cash")
                # DİQQƏT: type=SUPPLIER_PAYMENT (EXPENSE YOX) — bu məbləğ artıq repair.cost_price-ın
                # (maya dəyəri) özüdür və Hesabatlarda "total_cost" buradan hesablanır. Əgər bunu
                # EXPENSE kimi yazsaq, Hesabatlardakı "xərclər" sətri bu məbləği BİR DƏ çıxarar —
                # eyni 100 AZN həm maya dəyərində, həm də "xərc"də görünüb xalis mənfəəti iki dəfə
                # azaldardı. SUPPLIER_PAYMENT, təchizatçıya edilən bütün ödənişlərlə eyni kateqoriyada
                # olduğu üçün (bax: suppliers/views.py) Kassa balansına təsiri eynidir, amma Hesabat
                # mənfəət hesablamasına (yalnız EXPENSE-i çıxan) ikinci dəfə daxil olmur.
                CashTransaction.objects.create(
                    shop=repair.shop, branch=repair.branch, type=TransactionType.SUPPLIER_PAYMENT,
                    amount=repair.cost_price, method="cash",
                    expense_category="Xarici usta ödənişi",
                    description=f"{repair.number}, {repair.customer.full_name} — ustaya ({repair.technician_name}) ödənildi",
                    repair=repair, created_by=request.user,
                )

            # "Detal mənbəyi": təchizatçıdan borcla / nağd alındı.
            cost = repair.cost_price or 0
            if part_mode in ("credit", "cash") and cost and cost > 0:
                desc = (part_description or repair.issue_description or "Detal").strip()
                full_desc = f"{desc} — {repair.device_brand} {repair.device_model} ({repair.number})".strip()
                if part_supplier_id:
                    from suppliers.models import Supplier, SupplierPurchase, SupplierPurchasePayment
                    try:
                        supplier = Supplier.objects.get(pk=part_supplier_id, shop=repair.shop)
                    except Supplier.DoesNotExist:
                        raise ValidationError({"detail": "Seçilmiş təchizatçı tapılmadı."})
                    paid_amount = cost if part_mode == "cash" else 0
                    if paid_amount > 0:
                        from finance.models import assert_sufficient_balance
                        assert_sufficient_balance(repair.shop, paid_amount, part_payment_method)
                    purchase = SupplierPurchase.objects.create(
                        shop=repair.shop, supplier=supplier, description=full_desc,
                        amount=cost, paid_amount=paid_amount, repair=repair,
                    )
                    if paid_amount > 0:
                        SupplierPurchasePayment.objects.create(purchase=purchase, amount=paid_amount, method=part_payment_method)
                        from finance.models import CashTransaction, TransactionType
                        CashTransaction.objects.create(
                            shop=repair.shop, branch=repair.branch,
                            type=TransactionType.SUPPLIER_PAYMENT, amount=paid_amount, method=part_payment_method,
                            description=f"{supplier.name} — {full_desc}",
                            supplier=supplier, repair=repair, created_by=request.user,
                        )
                elif part_mode == "cash":
                    # Təchizatçı seçilməyib, sadəcə "Nağd/kartla aldım — borcsuz" — birbaşa
                    # Kassadan Xərc kimi yazılır, seçilmiş üsulun ÖZ balansı yoxlanır (nağdsa
                    # nağd balansı, kartla/bank köçürməsiylə alınıbsa kart balansı).
                    from finance.models import CashTransaction, TransactionType, assert_sufficient_balance
                    assert_sufficient_balance(repair.shop, cost, part_payment_method)
                    CashTransaction.objects.create(
                        shop=repair.shop, branch=repair.branch, type=TransactionType.EXPENSE,
                        amount=cost, method=part_payment_method, description=full_desc,
                        repair=repair, created_by=request.user,
                    )
                # part_mode == "credit" təchizatçısız — borc kimə aid ediləcəyi bilinmir,
                # ona görə heç nə yaradılmır (frontend bunu seçməyə məcbur edir).

            # İlkin ödəniş (addım 4) — əvvəllər təmir yaradıldıqdan sonra AYRICA sorğu ilə
            # göndərilirdi; indi eyni tranzaksiyadadır. DİQQƏT: bu, Kassaya pul ƏLAVƏ edən
            # (INCOME) bir əməliyyatdır, ona görə assert_sufficient_balance BURADA tətbiq
            # OLUNMUR — həmin yoxlama yalnız kassadan pul ÇIXAN (EXPENSE və s.) əməliyyatlar
            # üçündür (bax: RepairPaymentCreateSerializer.save() — orada da yoxdur).
            if initial_payment_amount and initial_payment_amount > 0:
                from .models import RepairPayment
                RepairPayment.objects.create(
                    repair=repair, amount=initial_payment_amount, method=initial_payment_method,
                    received_by=request.user,
                )
                from finance.models import CashTransaction, TransactionType
                CashTransaction.objects.create(
                    shop=repair.shop, branch=repair.branch, type=TransactionType.INCOME,
                    amount=initial_payment_amount, method=initial_payment_method,
                    description=f"{repair.number}, {repair.customer.full_name}",
                    repair=repair, created_by=request.user,
                )
                if hasattr(repair, "_prefetched_objects_cache"):
                    repair._prefetched_objects_cache.pop("payments", None)
                repair.recompute_payment_status()

        return repair


class RepairStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=RepairStatus.choices)

    def save(self, **kwargs):
        from django.utils import timezone
        from django.db import transaction
        # DİQQƏT: `Decimal` import YALNIZ funksiyanın ƏVVƏLİNDƏ olmalıdır — Python-da bir
        # funksiya daxilində hər hansı yerdə (hətta aşağıdaki "elif" qolunda) "import" olsa,
        # həmin ad funksiyanın BAŞDAN-SONA hər yerində "local" sayılır, yuxarıdaki "if" qolu
        # da daxil olmaqla. Əvvəllər bu import aşağıda (yalnız "elif" qolunda) idi və bu,
        # yuxarıdaki "if" qolundaki `lambda: Decimal("0")`-un işə düşən zaman "Decimal" adını
        # tapa bilməməsinə (NameError) səbəb olurdu.
        from decimal import Decimal
        repair: RepairOrder = self.context["repair"]
        new_status = self.validated_data["status"]
        old_status = repair.status
        changed = new_status != old_status
        # Hamısı bir tranzaksiyadadır: ləğv edərkən kassa yoxlaması (#56) uğursuz olub
        # ValidationError atsa, təmirin statusu da "CANCELLED" kimi yarım-yolda qalmamalıdır —
        # əks halda status dəyişmiş, amma pul geri qaytarılmamış/qeydə alınmamış olardı.
        with transaction.atomic():
            repair.status = new_status
            if new_status == RepairStatus.DELIVERED and not repair.delivered_at:
                repair.delivered_at = timezone.now()
                repair.warranty_started_at = timezone.now().date()
            repair.save()
            if changed and new_status == RepairStatus.CANCELLED:
                # Təmir ləğv edilir — ona bağlı təchizatçı alışları da "ləğv edildi" kimi işarələnir
                # (silinmir, tarixçədə qalır), ümumi təchizatçı borcundan isə çıxır.
                from suppliers.models import PurchaseStatus
                repair.supplier_purchases.update(status=PurchaseStatus.CANCELLED)
                # Bu təmirə görə müştəridən artıq real pul alınıbsa (kassaya "Kassa"/gəlir kimi
                # düşübsə), ləğv edəndə onu silmirik (maliyyə tarixçəsi qorunur), əvəzinə eyni
                # məbləğdə "Geri qaytarma" qeydi əlavə edirik ki, Kassa balansı özü-özünə düzəlsin —
                # müştəri "ləğv etdim, amma kassada qalır" şikayəti elə bunun üçün idi.
                from collections import defaultdict
                from finance.models import CashTransaction, TransactionType, compute_cashbox_summary

                # DİQQƏT: geri qaytarma/geri alma HƏR ÖDƏNİŞ ÜSULUNA (method) GÖRƏ AYRI
                # hesablanır — məs. müştəri kartla ödəyibsə, geri qaytarma da kartdan
                # yazılmalıdır, nağddan yox (əvvəllər bura baxmadan həmişə method="cash"
                # yazılırdı, nəticədə kartla edilən ödənişin ləğvi nağd balansını səhvən
                # azaldırdı, kart balansı isə "ödənilib" göstərməyə davam edirdi).
                net_received_by_method: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
                for t in CashTransaction.objects.filter(
                        repair=repair, type__in=[TransactionType.INCOME, TransactionType.REFUND]):
                    net_received_by_method[t.method] += t.amount if t.type == TransactionType.INCOME else -t.amount

                # Bu təmirə görə artıq təchizatçıya/xarici ustaya ödənilmiş məbləğ varsa (birbaşa
                # usta ödənişi və ya alış zamanı "dərhal ödənildi" seçimi ilə), müştəri qeyd etdi ki,
                # xidmət ləğv olunanda kassa mənfiyə düşməməlidir — yəni bu pul da geri alınmış sayılır
                # (usta/təchizatçıdan geri tələb olunur). Ona görə eyni məbləğdə (eyni method ilə)
                # EXPENSE_REFUND yazırıq ki, hər balans bu əməliyyatdan əvvəlki vəziyyətinə qayıtsın.
                #
                # DİQQƏT: "təchizatçıya nə qədər ödənilib" sualını YALNIZ bu təmirə bağlı
                # CashTransaction-lardan (repair=repair) tapmaq KİFAYƏT DEYİL — çünki təchizatçı
                # borcu SONRADAN Təchizatçılar səhifəsindəki "Borc ödə" ilə ödənəndə (bax:
                # suppliers/views.py SupplierViewSet.pay), yaradılan CashTransaction heç bir
                # repair FK-sı DAŞIMIR (FIFO ilə bir neçə alışa/təmirə bölünə bildiyi üçün) —
                # yalnız SupplierPurchasePayment (purchase.repair ilə) bu konkret təmirə bağlıdır.
                # Bunu nəzərə almasaq, "borcla alıb sonra borcu ödə, sonra ləğv et" ssenarisində
                # ödənilmiş pul HEÇ VAXT geri qaytarılmır — məhz bu şikayət idi.
                from suppliers.models import SupplierPurchasePayment

                paid_out_by_method: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
                # (1) Birbaşa bu təmirə yazılan, təchizatçısız əməliyyatlar — xarici usta ödənişi
                # (type=SUPPLIER_PAYMENT, supplier=None) və təchizatçısız "nağd/kart aldım" xərci
                # (type=EXPENSE, supplier=None, heç bir SupplierPurchase yaradılmır).
                for t in CashTransaction.objects.filter(
                        repair=repair, type__in=[TransactionType.SUPPLIER_PAYMENT, TransactionType.EXPENSE],
                        supplier__isnull=True):
                    paid_out_by_method[t.method] += t.amount
                # (2) Bu təmirin təchizatçı alış(lar)ına edilmiş BÜTÜN ödənişlər — istər təmir
                # yaradılanda dərhal (bu da ayrıca yuxarıdakı kimi CashTransaction yaradır, amma
                # supplier dolu olduğu üçün (1)-də sayılmır, təkrar hesablanmır), istərsə də
                # sonradan Təchizatçılar səhifəsindən borc ödənişi kimi.
                for p in SupplierPurchasePayment.objects.filter(purchase__repair=repair):
                    paid_out_by_method[p.method or "cash"] += p.amount
                already_recovered_by_method: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
                for t in CashTransaction.objects.filter(repair=repair, type=TransactionType.EXPENSE_REFUND):
                    already_recovered_by_method[t.method] += t.amount
                to_recover_by_method = {
                    m: paid_out_by_method[m] - already_recovered_by_method[m]
                    for m in paid_out_by_method
                }

                # Ləğvin hər üsul üzrə XALİS effekti: müştəriyə geri qaytarılan (-net_received)
                # və təchizatçı/ustadan geri alınan (+to_recover) BİRGƏ, EYNİ ÜSUL daxilində
                # hesablanır — əks halda (məs. yalnız REFUND-u ayrıca yoxlasaq) EXPENSE_REFUND-un
                # həmin an həmin balansa qaytaracağı pulu nəzərə almadan, əslində kifayət edən
                # balansı səhvən "yetərsiz" sayıb ləğvi lüzumsuz bloklaya bilərdik. #56: heç bir
                # balans mənfiyə düşməməlidir — bu yoxlama olmadan REFUND hər zaman yaradılır və
                # balans sakitcə mənfiyə enirdi.
                all_methods = set(net_received_by_method) | set(to_recover_by_method)
                summary = compute_cashbox_summary(repair.shop)
                for method in all_methods:
                    net_cash_effect = to_recover_by_method.get(method, Decimal("0")) - net_received_by_method.get(method, Decimal("0"))
                    if net_cash_effect >= 0:
                        continue
                    current = summary["current_balance"] if method == "cash" else summary["card_balance"]
                    if current + net_cash_effect < 0:
                        from rest_framework.exceptions import ValidationError
                        label = "Kassada" if method == "cash" else "Kart/bank balansında"
                        raise ValidationError({
                            "detail": f"{label} vəsait yoxdur — ləğv üçün {-net_cash_effect} AZN lazımdır, "
                                      f"cari balans isə {current} AZN. Əvvəlcə balansa pul əlavə edin."
                        })

                request = self.context.get("request")
                for method, net_received in net_received_by_method.items():
                    if net_received > 0:
                        CashTransaction.objects.create(
                            shop=repair.shop, branch=repair.branch, type=TransactionType.REFUND,
                            amount=net_received, method=method,
                            description=f"{repair.number}, {repair.customer.full_name} — xidmət ləğv edildi, ödəniş geri qaytarıldı",
                            repair=repair, created_by=getattr(request, "user", None),
                        )
                for method, to_recover in to_recover_by_method.items():
                    if to_recover > 0:
                        CashTransaction.objects.create(
                            shop=repair.shop, branch=repair.branch, type=TransactionType.EXPENSE_REFUND,
                            amount=to_recover, method=method,
                            description=f"{repair.number}, {repair.customer.full_name} — xidmət ləğv edildi, təchizatçı/ustaya ödənilən məbləğ geri alındı",
                            repair=repair, created_by=getattr(request, "user", None),
                        )
            elif changed and old_status == RepairStatus.CANCELLED:
                # Ləğv edilmiş təmir yenidən aktivləşdirilirsə, bağlı alışlar da geri aktivləşir
                # və maya dəyəri yenidən onların cəminə görə hesablanır.
                from suppliers.models import PurchaseStatus, sync_repair_cost_price
                repair.supplier_purchases.filter(status=PurchaseStatus.CANCELLED).update(status=PurchaseStatus.ACTIVE)
                sync_repair_cost_price(repair)

                # DİQQƏT (əsas düzəliş, video ilə göstərilən xəta): ləğv ediləndə yuxarıda (bax
                # "if ... CANCELLED" bloku) müştərinin ödənişi REFUND kimi Kassadan çıxılır, ustaya/
                # təchizatçıya ödənilən məbləğ isə EXPENSE_REFUND kimi geri "bərpa" olunur. Əvvəllər
                # xidmət YENİDƏN aktivləşdiriləndə (Ləğv edildi → Təhvil verildi və s.) bu HEÇ VAXT
                # TƏRSİNƏ ÇEVRİLMİRDİ — RepairPayment qeydi (və "Ödənilib" göstəricisi) toxunulmaz
                # qaldığı üçün təmirin özü hələ də "ödənilib" görünürdü, AMMA Kassa balansı itirdiyi
                # pulu BİR DAHA GERİ ALMIRDI — nəticədə hər ləğv+bərpa dövründə kassa həqiqi
                # vəziyyətdən getdikcə geri qalırdı ("itən" pul). İndi: bu təmirə bağlı REFUND/
                # EXPENSE_REFUND-un XALİS (hələ bərpa olunmamış) hissəsi hər ödəniş üsulu üzrə ayrıca
                # hesablanır və tərs əməliyyatla (REFUND → INCOME, EXPENSE_REFUND → SUPPLIER_PAYMENT)
                # bərpa olunur — #56 tələbinə uyğun, balans kifayət etmirsə (çox nadir hal, yalnız
                # ustaya/təchizatçıya yenidən "ödəniləcək" tərəf üçün mümkündür) əməliyyat dayandırılır.
                from collections import defaultdict
                from finance.models import CashTransaction, TransactionType, compute_cashbox_summary, assert_sufficient_balance

                # DİQQƏT: "bərpa olundu" sözü BİLƏRƏKDƏN marker kimi istifadə olunur — aşağıda
                # YALNIZ bu sözü olan INCOME/SUPPLIER_PAYMENT yazıları "artıq bərpa edilmiş" kimi
                # sayılır, orijinal (ilk ödəniş/ilk usta ödənişi) yazıları YOX. Əks halda — yəni
                # bütün INCOME-u REFUND-dan çıxsaq — ilk ödəniş elə REFUND-un özü ilə "sıfırlanar"
                # və bərpa heç vaxt yaradılmazdı (REFUND elə o ilk ödənişi ləğv etmək üçün
                # yaradılmışdı, ona qarşı hesablanmamalıdır). Bu sayədə dəfələrlə ləğv/bərpa
                # dövrü edilsə belə (hər dövr öz REFUND-unu yaradır), hesab düzgün qalır.
                RESTORE_MARK = "yenidən aktivləşdirildi"

                refunded_by_method: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
                already_restored_income_by_method: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
                for t in CashTransaction.objects.filter(repair=repair, type__in=[TransactionType.INCOME, TransactionType.REFUND]):
                    if t.type == TransactionType.REFUND:
                        refunded_by_method[t.method] += t.amount
                    elif RESTORE_MARK in (t.description or ""):
                        already_restored_income_by_method[t.method] += t.amount

                recovered_by_method: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
                already_restored_payment_by_method: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
                for t in CashTransaction.objects.filter(repair=repair, type__in=[TransactionType.SUPPLIER_PAYMENT, TransactionType.EXPENSE_REFUND]):
                    if t.type == TransactionType.EXPENSE_REFUND:
                        recovered_by_method[t.method] += t.amount
                    elif RESTORE_MARK in (t.description or ""):
                        already_restored_payment_by_method[t.method] += t.amount

                request = self.context.get("request")

                # Müştəridən alınan, amma hələ bərpa olunmamış (son ləğvdə geri qaytarılan) hissə —
                # yenidən "Kassa" (INCOME) kimi yazılır ki, balans əvvəlki kimi düzəlsin.
                for method, refunded in refunded_by_method.items():
                    to_restore = refunded - already_restored_income_by_method.get(method, Decimal("0"))
                    if to_restore > 0:
                        CashTransaction.objects.create(
                            shop=repair.shop, branch=repair.branch, type=TransactionType.INCOME,
                            amount=to_restore, method=method,
                            description=f"{repair.number}, {repair.customer.full_name} — xidmət {RESTORE_MARK}, ödəniş bərpa olundu",
                            repair=repair, created_by=getattr(request, "user", None),
                        )

                # Təchizatçıdan/ustadan "geri alınmış" sayılan, amma hələ yenidən ödənilməmiş hissə —
                # balans kifayət edirsə yenidən Təchizatçı ödənişi kimi yazılır (kifayət etmirsə,
                # #56-ya uyğun, bu hissə üçün əməliyyat dayandırılır).
                for method, recovered in recovered_by_method.items():
                    to_repay = recovered - already_restored_payment_by_method.get(method, Decimal("0"))
                    if to_repay > 0:
                        assert_sufficient_balance(repair.shop, to_repay, method)
                        CashTransaction.objects.create(
                            shop=repair.shop, branch=repair.branch, type=TransactionType.SUPPLIER_PAYMENT,
                            amount=to_repay, method=method,
                            description=f"{repair.number}, {repair.customer.full_name} — xidmət {RESTORE_MARK}, təchizatçı/ustaya ödəniş bərpa olundu",
                            repair=repair, created_by=getattr(request, "user", None),
                        )
            if changed:
                # Hər status dəyişikliyinin vaxtı qeydə alınır ("nə vaxtdan təmir prosesindədir",
                # "nə vaxtdan hazırdır" və s. sualları üçün — bax RepairStatusHistory).
                RepairStatusHistory.objects.create(repair=repair, status=new_status)
            # Status dəyişəndə (xüsusən 'Təhvil verildi'-yə keçəndə) ödəniş statusunu
            # yenidən hesabla — qalıq borc varsa indi 'debt' kimi işarələnəcək.
            repair.recompute_payment_status()
        return repair


class RepairPaymentCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    method = serializers.ChoiceField(choices=RepairPayment._meta.get_field("method").choices)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Məbləğ sıfırdan böyük olmalıdır.")
        repair: RepairOrder = self.context["repair"]
        remaining = repair.remaining_debt
        if remaining > 0 and value > remaining:
            raise serializers.ValidationError(
                f"Ödəniş qalıq borcdan ({remaining} AZN) çox ola bilməz."
            )
        return value

    def save(self, **kwargs):
        repair: RepairOrder = self.context["repair"]
        request = self.context["request"]
        payment = RepairPayment.objects.create(
            repair=repair, amount=self.validated_data["amount"],
            method=self.validated_data["method"], received_by=request.user,
        )
        from finance.models import CashTransaction, TransactionType
        CashTransaction.objects.create(
            shop=repair.shop, branch=repair.branch, type=TransactionType.INCOME,
            amount=payment.amount, method=payment.method,
            description=f"{repair.number}, {repair.customer.full_name}",
            repair=repair, created_by=request.user,
        )
        # repair.payments queryset ola bilsin artıq keşlənib (məs. viewset-in
        # prefetch_related-i vasitəsilə) — yuxarıdakı create() bu keşi yeniləmir,
        # ona görə borcu düzgün hesablamaq üçün keşi təmizləyirik.
        if hasattr(repair, "_prefetched_objects_cache"):
            repair._prefetched_objects_cache.pop("payments", None)
        repair.recompute_payment_status()
        return payment