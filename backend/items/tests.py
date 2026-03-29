from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from items.admin import GradeSyncUserAdmin, gradesync_admin


def _fieldset_field_names(admin_class, request, obj):
    ma = admin_class(User, gradesync_admin)
    names = []
    for _title, opts in ma.get_fieldsets(request, obj):
        for f in opts.get("fields", ()):
            if isinstance(f, (list, tuple)):
                names.extend(f)
            else:
                names.append(f)
    return names


class GradeSyncUserAdminSuperuserTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.request = self.rf.get("/admin/")
        self.request.user = User.objects.create_user(
            "staff_editor", password="pw", is_staff=True
        )

    def test_change_form_fieldsets_exclude_is_superuser(self):
        target = User.objects.create_user("target", password="pw")
        names = _fieldset_field_names(GradeSyncUserAdmin, self.request, target)
        self.assertNotIn("is_superuser", names)

    def test_add_form_fieldsets_exclude_is_superuser(self):
        names = _fieldset_field_names(GradeSyncUserAdmin, self.request, None)
        self.assertNotIn("is_superuser", names)

    def test_save_model_cannot_clear_superuser_via_admin(self):
        target = User.objects.create_user(
            "su", password="pw", is_staff=True, is_superuser=True
        )
        ma = GradeSyncUserAdmin(User, gradesync_admin)
        target.is_superuser = False
        ma.save_model(self.request, target, form=None, change=True)
        target.refresh_from_db()
        self.assertTrue(target.is_superuser)

    def test_save_model_cannot_grant_superuser_on_create(self):
        ma = GradeSyncUserAdmin(User, gradesync_admin)
        u = User(username="newu", email="n@example.com", is_superuser=True)
        ma.save_model(self.request, u, form=None, change=False)
        self.assertFalse(u.is_superuser)
