from django.contrib import admin
from django import forms
from ..models import Waypoint, WaypointViewImage, WaypointViewLink, TypeOfImage
from django.forms.widgets import ClearableFileInput
from django.utils.safestring import mark_safe
from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _

class MultipleClearableFileInput(ClearableFileInput):
    
    def __init__(self, attrs=None):
        super().__init__(attrs)
        if self.attrs is None:
            self.attrs = {}
        self.attrs['multiple'] = True
        self.attrs['accept'] = 'image/*'
        
    def render(self, name, value, attrs=None, renderer=None):
        input_html = super().render(name, value, attrs, renderer)
        return mark_safe(f"""
        <div class="image-upload-container">
            <div class="flex w-full max-w-2xl items-center justify-between gap-2 rounded-default border border-base-200 px-3 py-2 shadow-xs dark:border-base-700">
                <label class="text-sm font-medium text-base-700 dark:text-base-200">
                    {input_html}
                </label>
            </div>
        </div>
        """)


class WaypointForm(forms.ModelForm):
    
    position = forms.IntegerField(required=False, widget=forms.HiddenInput())
    
    uploaded_images = forms.FileField(
        required=False,
        label=_('📷 Add Images'),
        widget=MultipleClearableFileInput(),
        help_text=_('Upload photos that best represent this location')
    )

    additional_images = forms.FileField(
        required=False,
        label=_('📷 Add Specific Images for this Waypoint'),
        widget=MultipleClearableFileInput(),
        help_text=_('Upload photos that best represent this waypoint')
    )

    links = forms.CharField(
        required=False,
        label=_('🔗 Add Links'),
        widget=forms.Textarea(attrs={
            'rows': 5,
            'class': 'vTextField',
            'placeholder': _('Enter one link per line:\n\n'
                        'https://en.wikipedia.org/wiki/Milan_Cathedral\n'
                        'https://www.duomomilano.it\n'
                        'https://www.youtube.com/watch?v=example'),
        }),
        help_text=_('🔗 Enter one link per line. Each line will be saved as a separate link. '
                'You can add official websites, Wikipedia, YouTube videos, etc.')
    )
    
    readme_text = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'markdown-editor', 
            'rows': 10,
            'placeholder': _('Write the detailed description here using Markdown...\n\n'
                          '**Example:**\n'
                          '# Title\n'
                          '## Subtitle\n'
                          '- Bullet list\n'
                          '- Another point\n\n'
                          'Normal text with **bold** and *italic*')
        }),
        label=_("📝 Detailed Description (Markdown)"),
        required=False,
        help_text=_('Use Markdown to format the complete description. You can include titles, lists, bold, italic, etc.')
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.instance and self.instance.pk and self.instance.readme_item:
            try:
                self.fields['readme_text'].initial = self.instance.readme_item.read().decode('utf-8')
            except Exception as e:
                print(f"Error loading readme: {e}")
        
        if self.instance and self.instance.pk:
            existing_links = WaypointViewLink.objects.filter(waypoint=self.instance)
            if existing_links.exists():
                self.fields['links'].initial = '\n'.join([link.link for link in existing_links if link.link])

        if 'coordinates' in self.fields:
            old_classes = self.fields['coordinates'].widget.attrs.get('class', '')
            new_classes = f"{old_classes} waypoint-coordinates-field".strip()
            self.fields['coordinates'].widget.attrs['class'] = new_classes
        
        field_configs = {
            'title': {
                'help_text': _('🏛️ The name of this point of interest (e.g.: "Milan Cathedral", "Sforza Castle")'),
                'widget_attrs': {'placeholder': _('E.g.: Milan Cathedral')}
            },
            'place': {
                'help_text': _('📍 City or location (e.g.: "Milan", "Florence")'),
                'widget_attrs': {'placeholder': _('E.g.: Milan')}
            },
            'description': {
                'help_text': _('✍️ A brief description that will appear in the list of points (max 2-3 lines)'),
                'widget_attrs': {
                    'placeholder': _('E.g.: Masterpiece of Gothic architecture, symbol of the city...'),
                    'rows': 3
                }
            },
            'coordinates': {
                'help_text': _('🗺️ Click on the map to select the exact position of the point')
            },
            'pdf_item': {
                'help_text': _('📄 Upload a PDF with additional information (optional)')
            },
            'video_item': {
                'help_text': _('🎥 Upload a descriptive video (optional)')
            },
            'audio_item': {
                'help_text': _('🎵 Upload an audio guide (optional)')
            }
        }
        
        for field_name, config in field_configs.items():
            if field_name in self.fields:
                self.fields[field_name].help_text = config['help_text']
                if 'widget_attrs' in config:
                    self.fields[field_name].widget.attrs.update(config['widget_attrs'])

    def clean_uploaded_images(self):
        field_name = self.add_prefix('uploaded_images')
        try:
            return self.files.getlist(field_name)
        except Exception:
            return []
    
    def clean_additional_images(self):
        field_name = self.add_prefix('additional_images')
        try:
            return self.files.getlist(field_name)
        except Exception:
            return []
    
    def clean_links(self):
        links_text = self.cleaned_data.get('links', '')
        if not links_text:
            return []
        
        links = [link.strip() for link in links_text.strip().split('\n') if link.strip()]
        
        valid_links = []
        for link in links:
            if link and not link.startswith(('http://', 'https://')):
                link = 'https://' + link
            valid_links.append(link)
        
        return valid_links
            
    def save(self, commit=True):
        instance = super().save(commit=commit)
        
        if commit and hasattr(self, 'cleaned_data'):
            uploaded_files = self.cleaned_data.get('uploaded_images', [])
            for uploaded_file in uploaded_files:
                WaypointViewImage.objects.create(waypoint=instance, image=uploaded_file, type_of_images=TypeOfImage.DEFAULT)
        
        if commit and hasattr(self, 'cleaned_data'):
            additional_images = self.cleaned_data.get('additional_images', [])
            for additional_image in additional_images:
                WaypointViewImage.objects.create(waypoint=instance, image=additional_image, type_of_images=TypeOfImage.ADDITIONAL_IMAGES)

        if commit and hasattr(self, 'cleaned_data'):
            readme_text = self.cleaned_data.get('readme_text')
            if readme_text:
                instance.readme_item = ContentFile(readme_text.encode('utf-8'), name='readme.md')
                instance.save()
        
        if commit and hasattr(self, 'cleaned_data'):
            links = self.cleaned_data.get('links', [])
            
            WaypointViewLink.objects.filter(waypoint=instance).delete()
            
            for link in links:
                if link:
                    WaypointViewLink.objects.create(waypoint=instance, link=link)
        
        return instance

    class Meta:
        model = Waypoint
        fields = ['title', 'place', 'coordinates', 'description', 'pdf_item', 'video_item', 'audio_item', 'position']
        widgets = { 'position': forms.HiddenInput() }