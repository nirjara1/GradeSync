from django import forms
from .models import Course

class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['title', 'crn', 'term', 'section', 'grading_default', 'unweighted', 'visibility', 'published', 'code']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'e.g. Database System'}),
            'crn': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Enter 5-digit CRN'}),
            'term': forms.TextInput(attrs={'class': 'input-field'}),
            'section': forms.TextInput(attrs={'class': 'input-field'}),
            'code': forms.HiddenInput(),
            'grading_default': forms.CheckboxInput(attrs={'class': 'ui-toggle'}),
            'unweighted': forms.CheckboxInput(attrs={'class': 'ui-toggle'}),
            'visibility': forms.CheckboxInput(attrs={'class': 'ui-toggle'}),
            'published': forms.CheckboxInput(attrs={'class': 'ui-toggle'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['code'].required = False  # Make generic code optional
        self.fields['code'].initial = 'GENERIC'
