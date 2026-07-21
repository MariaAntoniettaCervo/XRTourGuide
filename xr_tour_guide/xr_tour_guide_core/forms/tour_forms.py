from django import forms
from ..models import Tour

from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

class ClickableCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    
    def __init__(self, model_name='tour', app_label='xr_tour_guide_core', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model_name = model_name
        self.app_label = app_label
    
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        
        if value:
            # print(f"VALUE: {value}", flush=True)
            change_url = reverse(f'admin:{self.app_label}_{self.model_name}_change', args=[value])
            
            original_label = option['label']
            option['label'] = format_html(
                '{} <a href="{}" target="_blank" style="margin-left: 8px; color: #3b82f6; text-decoration: none; font-weight: 500;" '
                'onclick="event.stopPropagation();">✏️ {}</a>',
                original_label,
                change_url,
                _('Edit')
            )
        
        return option
    
    class Media:
        css = {
            # 'all': ['admin/css/clickable_checkboxes.css']
        }

class TourForm(forms.ModelForm):
    
    class Meta:
        model = Tour
        fields = "__all__"
        widgets = {
            'is_subtour': forms.HiddenInput(),
            'sub_tours': ClickableCheckboxSelectMultiple(
                model_name='tour',
                app_label='xr_tour_guide_core'
            ),
        }
        labels = {
            'sub_tours': _('🔗 Internal Tours'),
            'title': _('🎯 Tour Title'),
            'subtitle': _('📌 Subtitle'),
            'description': _('📝 Description'),
            'place': _('📍 Location'),
            'coordinates': _('🗺️ Map Coordinates'),
            'default_image': _('🖼️ Cover Image'),
            'category': _('🏷️ Category'),
            'language': _('🌐 Language'),
        }
        help_texts = {
            'title': _('A catchy and clear title (e.g.: "Historic Center Tour", "Journey Through Art and History")'),
            'subtitle': _('A phrase that captures the essence of the tour in a few words'),
            'description': _('Complete description: what will be seen, how long it lasts, what makes it special'),
            'place': _('The main city or area of the tour'),
            'default_image': _('A suggestive image that represents the tour'),
            'sub_tours': _('Select internal tours. Click on "✏️ Edit" to open and modify each tour.'),
            'category': _('The type of experience offered'),
            'language': _('The language of the tour'),
        }

    def __init__(self, *args, **kwargs):
        request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        if 'sub_tours' in self.fields:
            self.fields['sub_tours'].widget.attrs.update({
                'class': 'unfold-multiselect flex flex-col gap-2 p-2 border rounded-lg bg-white shadow-sm'
            })
        
        if 'title' in self.fields:
            self.fields['title'].widget.attrs['placeholder'] = _('E.g.: Historic Center Tour of Rome')
        if 'subtitle' in self.fields:
            self.fields['subtitle'].widget.attrs['placeholder'] = _('E.g.: Discovering the most iconic monuments')
        if 'description' in self.fields:
            self.fields['description'].widget.attrs['placeholder'] = _(
                'Describe the tour in an engaging way:\n'
                '- What will be seen\n'
                '- Estimated duration\n'
                '- What makes it special\n'
                '- Who it is recommended for'
            )
        if 'place' in self.fields:
            self.fields['place'].widget.attrs['placeholder'] = _('E.g.: Rome')

        if request and "_popup" in request.GET and not self.instance.pk:
            if 'category' in self.fields:
                self.fields['category'].initial = 'INDOOR'
                self.fields['category'].disabled = True
                self.fields['category'].widget = forms.HiddenInput()
            if 'is_subtour' in self.fields:
                self.fields['is_subtour'].initial = True