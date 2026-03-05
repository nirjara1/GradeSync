from django import forms
from .models import Course, UserProfile
from django.contrib.auth.models import User

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

class UserRegistrationForm(forms.Form):
    email = forms.EmailField(
        label='Email or Username',
        widget=forms.EmailInput(attrs={'id': 'username', 'placeholder': ' ', 'autocomplete': 'username'})
    )
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'id': 'password', 'placeholder': ' ', 'autocomplete': 'new-password'})
    )
    password_confirm = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={'id': 'password_confirm', 'placeholder': ' ', 'autocomplete': 'new-password'})
    )
    role = forms.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        label='Account Type',
        widget=forms.Select(attrs={'id': 'role', 'class': 'input-group-select'})
    )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(username=email).exists() or User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', "Passwords do not match.")
        
        return cleaned_data
