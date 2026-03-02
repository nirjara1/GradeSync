from django import forms
from .models import Assignment, Submission

class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ['name', 'description', 'course', 'points', 'due_date', 'no_due_date', 'allowed_language', 'public_test_data', 'expected_outputs', 'status']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'required': True, 'placeholder': 'Assignment Title'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Description'}),
            'course': forms.Select(attrs={'class': 'form-control'}),
            'points': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'due_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'no_due_date': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allowed_language': forms.RadioSelect(attrs={'class': 'form-check-input'}),
            'public_test_data': forms.FileInput(attrs={'class': 'form-control-file', 'style': 'display: none;', 'id': 'public_test_data_upload'}),
            'expected_outputs': forms.FileInput(attrs={'class': 'form-control-file', 'style': 'display: none;', 'id': 'expected_outputs_upload'}),
            'status': forms.HiddenInput(),
        }
        labels = {
            'name': 'Assignment Title',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['points'].required = False
        self.fields['status'].required = False
        self.fields['course'].required = False


class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ['file_path']
        widgets = {
            'file_path': forms.FileInput(attrs={'class': 'form-control-file', 'required': True}),
        }
        labels = {
            'file_path': 'Select File',
        }
