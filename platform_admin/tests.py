from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Role, User
from tenants.models import Plan, Shop
from .resources import RESOURCES, build_meta


class BaseCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name="Pro", price_monthly=50)
        cls.shop_a = Shop.objects.create(name="Alpha Servis", plan=cls.plan)
        cls.shop_b = Shop.objects.create(name="Beta Servis", plan=cls.plan)
        cls.role_a = Role.objects.create(shop=cls.shop_a, name="Sahib", is_owner_role=True)
        cls.role_b = Role.objects.create(shop=cls.shop_b, name="Sahib", is_owner_role=True)
        cls.owner_a = User.objects.create_user("owner.alpha", password="pass1234", shop=cls.shop_a, role=cls.role_a)
        cls.staff_a = User.objects.create_user("usta.alpha", password="pass1234", shop=cls.shop_a, role=cls.role_a)
        cls.owner_b = User.objects.create_user("owner.beta", password="pass1234", shop=cls.shop_b, role=cls.role_b)
        cls.superadmin = User.objects.create_user("superadmin", password="pass1234", is_platform_admin=True)
        # mağazası da olan platforma admini
        cls.hybrid = User.objects.create_user("hybrid", password="pass1234", shop=cls.shop_a, role=cls.role_a,
                                              is_platform_admin=True)

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c


class ShopUsersScopeTests(BaseCase):
    def usernames(self, user):
        r = self.client_for(user).get("/api/users/?page_size=100")
        self.assertEqual(r.status_code, 200)
        return {u["username"] for u in r.json()["results"]}

    def test_shop_owner_sees_only_own_shop_users(self):
        self.assertEqual(self.usernames(self.owner_a), {"owner.alpha", "usta.alpha"})
        self.assertEqual(self.usernames(self.owner_b), {"owner.beta"})

    def test_platform_admin_with_shop_still_sees_only_own_shop_on_users_page(self):
        names = self.usernames(self.hybrid)
        self.assertEqual(names, {"owner.alpha", "usta.alpha"})

    def test_platform_admin_without_shop_gets_empty_list_on_shop_page(self):
        self.assertEqual(self.usernames(self.superadmin), set())

    def test_created_user_belongs_to_current_shop(self):
        c = self.client_for(self.owner_a)
        r = c.post("/api/users/", {"username": "yeni.alpha", "first_name": "Yeni", "password": "abc12345",
                                   "role_id": self.role_a.id}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(User.objects.get(username="yeni.alpha").shop_id, self.shop_a.id)
        self.assertIn("yeni.alpha", self.usernames(self.owner_a))
        self.assertNotIn("yeni.alpha", self.usernames(self.owner_b))

    def test_cannot_assign_role_of_other_shop(self):
        r = self.client_for(self.owner_a).post(
            "/api/users/", {"username": "x.alpha", "password": "abc12345", "role_id": self.role_b.id}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_me_flags(self):
        self.assertFalse(self.client_for(self.owner_a).get("/api/auth/me/").json()["is_superadmin"])
        self.assertTrue(self.client_for(self.superadmin).get("/api/auth/me/").json()["is_superadmin"])


class PlatformAccessTests(BaseCase):
    def test_shop_users_are_forbidden(self):
        c = self.client_for(self.owner_a)
        for url in ("/api/platform/resources/", "/api/platform/r/users/", "/api/platform/r/shops/",
                    "/api/platform/dashboard/"):
            self.assertEqual(c.get(url).status_code, 403, url)

    def test_anonymous_is_rejected(self):
        self.assertEqual(APIClient().get("/api/platform/r/shops/").status_code, 401)


class PlatformCrudTests(BaseCase):
    def setUp(self):
        self.c = self.client_for(self.superadmin)

    def test_every_resource_lists_and_meta_resolves(self):
        keys = {r.key for r in RESOURCES}
        for res in RESOURCES:
            r = self.c.get(f"/api/platform/r/{res.key}/?page_size=5")
            self.assertEqual(r.status_code, 200, (res.key, r.content))
            meta = build_meta(res)
            names = {f["name"] for f in meta["fields"]}
            for col in res.columns:
                self.assertIn(col, names, (res.key, col))
            for f in meta["fields"]:
                if f["type"] == "related":
                    self.assertIn(f["related"], keys, (res.key, f["name"]))
        self.assertEqual(len(self.c.get("/api/platform/resources/").json()), len(RESOURCES))

    def test_shop_crud(self):
        r = self.c.post("/api/platform/r/shops/", {"name": "Alpha Servis", "plan": self.plan.id, "status": "active"},
                        format="json")
        self.assertEqual(r.status_code, 201, r.content)
        sid = r.json()["id"]
        self.assertEqual(r.json()["code"], "alpha-servis-2")  # unikal kod avtomatik
        self.assertEqual(r.json()["plan_display"], "Pro")
        r = self.c.patch(f"/api/platform/r/shops/{sid}/", {"city": "Bakı"}, format="json")
        self.assertEqual(r.json()["city"], "Bakı")
        self.assertEqual(self.c.delete(f"/api/platform/r/shops/{sid}/").status_code, 204)

    def test_user_crud_hashes_password_and_hides_it(self):
        r = self.c.post("/api/platform/r/users/", {
            "username": "kassir.beta", "first_name": "Kassir", "shop": str(self.shop_b.id),
            "role": self.role_b.id, "password": "gizli1234", "status": "active"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertNotIn("password", r.json())
        u = User.objects.get(username="kassir.beta")
        self.assertTrue(u.check_password("gizli1234"))
        r = self.c.patch(f"/api/platform/r/users/{u.id}/", {"password": "yeni12345"}, format="json")
        self.assertEqual(r.status_code, 200)
        u.refresh_from_db()
        self.assertTrue(u.check_password("yeni12345"))
        self.assertEqual(self.c.delete(f"/api/platform/r/users/{u.id}/").status_code, 204)

    def test_users_filter_by_shop_and_search(self):
        r = self.c.get(f"/api/platform/r/users/?shop={self.shop_b.id}").json()
        self.assertEqual({u["username"] for u in r["results"]}, {"owner.beta"})
        r = self.c.get("/api/platform/r/users/?search=usta").json()
        self.assertEqual([u["username"] for u in r["results"]], ["usta.alpha"])

    def test_cannot_delete_self(self):
        r = self.c.delete(f"/api/platform/r/users/{self.superadmin.id}/")
        self.assertEqual(r.status_code, 400)

    def test_role_and_permission_crud(self):
        r = self.c.post("/api/platform/r/roles/", {"shop": str(self.shop_a.id), "name": "Kassir"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        rid = r.json()["id"]
        perm = self.c.get(f"/api/platform/r/role-permissions/?role={rid}&module=cashbox").json()["results"][0]
        self.assertFalse(perm["is_allowed"])  # rol yaranan kimi bütün icazə sətirləri hazırdır
        r = self.c.patch(f"/api/platform/r/role-permissions/{perm['id']}/", {"is_allowed": True}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        dup = self.c.post("/api/platform/r/role-permissions/", {"role": rid, "module": "cashbox", "is_allowed": False},
                          format="json")
        self.assertEqual(dup.status_code, 400)


class RoleDefaultsTests(BaseCase):
    def test_new_role_gets_default_permissions_and_user_sees_modules(self):
        c = self.client_for(self.owner_a)
        r = c.post("/api/roles/", {"name": "Kassir"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        mods = {p["module"]: p["is_allowed"] for p in r.json()["permissions"]}
        self.assertEqual(len(mods), 12)
        self.assertTrue(mods["repairs"] and mods["customers"] and mods["inventory"])
        self.assertFalse(mods["cashbox"] or mods["users"] or mods["settings"])

        r = c.post("/api/users/", {"username": "kassir.alpha", "password": "abc12345", "role_id": r.json()["id"]},
                   format="json")
        self.assertEqual(r.status_code, 201, r.content)
        me = self.client_for(User.objects.get(username="kassir.alpha")).get("/api/auth/me/").json()
        self.assertEqual(set(me["allowed_modules"]), {"repairs", "customers", "inventory", "marketplace", "suppliers"})

    def test_permission_toggle_works_on_new_role(self):
        c = self.client_for(self.owner_a)
        rid = c.post("/api/roles/", {"name": "Usta2"}, format="json").json()["id"]
        r = c.patch(f"/api/roles/{rid}/permissions/", {"permissions": [{"module": "cashbox", "is_allowed": True}]},
                    format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Role.objects.get(pk=rid).has_permission("cashbox"))

    def test_user_without_role_is_rejected(self):
        r = self.client_for(self.owner_a).post("/api/users/", {"username": "rolsuz.alpha", "password": "abc12345"},
                                               format="json")
        self.assertEqual(r.status_code, 400)
