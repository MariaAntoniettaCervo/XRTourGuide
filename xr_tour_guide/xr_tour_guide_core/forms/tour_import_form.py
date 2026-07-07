from django import forms
from django.utils.translation import gettext_lazy as _


class TourImportForm(forms.Form):
    archive = forms.FileField(label=_("ZIP archive"))
    create_copy = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Create imported copy"),
        help_text=_("If enabled, imported tours will get a safe copied title."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["archive"].widget.attrs.update({
            "accept": ".zip,application/zip",
            "class": (
                "block w-full rounded-default border border-base-200 bg-white px-3 py-2 text-sm "
                "text-font-default shadow-xs transition focus:border-primary-500 focus:outline-none "
                "focus:ring-2 focus:ring-primary-200 dark:border-base-700 dark:bg-base-900 "
                "dark:text-font-important dark:focus:border-primary-500 dark:focus:ring-primary-500/20"
            ),
        })

        self.fields["create_copy"].widget.attrs.update({
            "class": (
                "h-4 w-4 rounded border-base-300 text-primary-600 focus:ring-primary-500 "
                "dark:border-base-600 dark:bg-base-800"
            ),
        })

    def clean_archive(self):
        archive = self.cleaned_data["archive"]
        if not archive.name.lower().endswith(".zip"):
            raise forms.ValidationError(_("Only ZIP archives are supported"))
        return archive