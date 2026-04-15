from django import forms
from .models import Assignment, Submission, TestCase, RuleSet
import json
import csv
import openpyxl

class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ['name', 'description', 'course', 'points', 'is_weighted', 'weight', 'due_date', 'no_due_date', 'allowed_language', 'public_test_data', 'status', 'is_group_assignment', 'max_group_size']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'required': True, 'placeholder': 'Assignment Title'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Description'}),
            'course': forms.Select(attrs={'class': 'form-control'}),
            'points': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'placeholder': 'Total Points'}),
            'is_weighted': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'weight': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01', 'placeholder': 'e.g., 10 (percent)'}),
            'due_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'no_due_date': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allowed_language': forms.RadioSelect(attrs={'class': 'form-check-input'}),
            'public_test_data': forms.FileInput(attrs={'class': 'form-control-file'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'is_group_assignment': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'max_group_size': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
        }
        labels = {
            'name': 'Assignment Title',
            'is_weighted': 'Weighted grading',
            'weight': 'Weight (%)',
            'max_group_size': 'Maximum Group Size',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['points'].required = False
        self.fields['status'].required = False
        self.fields['course'].required = False
        self.fields['public_test_data'].required = False
        self.fields['is_weighted'].required = False
        self.fields['weight'].required = False
        self.fields['is_group_assignment'].required = False
        self.fields['max_group_size'].required = False

    def clean(self):
        cleaned = super().clean()
        is_weighted = bool(cleaned.get("is_weighted"))
        weight = cleaned.get("weight")
        if is_weighted:
            if weight is None:
                self.add_error("weight", "Weight is required when weighted grading is enabled.")
            else:
                try:
                    w = float(weight)
                except (TypeError, ValueError):
                    self.add_error("weight", "Weight must be a number.")
                else:
                    if w <= 0:
                        self.add_error("weight", "Weight must be greater than 0.")
                    if w > 100:
                        self.add_error("weight", "Weight should be 100 or less (percent).")
        else:
            cleaned["weight"] = None
        return cleaned


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


class TestCaseUploadForm(forms.Form):
    """Form for uploading test cases in bulk via JSON, CSV, or Excel"""
    FILE_FORMAT_CHOICES = [
        ('json', 'JSON'),
        ('csv', 'CSV'),
        ('excel', 'Excel (.xlsx)'),
    ]
    
    test_file = forms.FileField(
        required=True,
        help_text='Upload a JSON, CSV, or Excel file with test cases',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.json,.csv,.xlsx',
        })
    )
    file_format = forms.ChoiceField(
        choices=FILE_FORMAT_CHOICES,
        required=True,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )
    clear_existing = forms.BooleanField(
        required=False,
        initial=False,
        help_text='Clear all existing test cases before importing',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    def clean(self):
        cleaned_data = super().clean()
        test_file = cleaned_data.get('test_file')
        file_format = cleaned_data.get('file_format')
        
        if test_file:
            # Validate file extension matches selected format
            filename = test_file.name.lower()
            if file_format == 'json' and not filename.endswith('.json'):
                raise forms.ValidationError('Selected JSON format but file is not .json')
            elif file_format == 'csv' and not filename.endswith('.csv'):
                raise forms.ValidationError('Selected CSV format but file is not .csv')
            elif file_format == 'excel' and not filename.endswith('.xlsx'):
                raise forms.ValidationError('Selected Excel format but file is not .xlsx')
        
        return cleaned_data


class TestCaseForm(forms.ModelForm):
    """Form for creating/editing individual test cases"""
    class Meta:
        model = TestCase
        fields = ['name', 'description', 'input_data', 'expected_output', 'is_hidden', 'order']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Test case 1',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe what this test case validates',
            }),
            'input_data': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Input data for the test case',
            }),
            'expected_output': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Expected output',
            }),
            'is_hidden': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
            }),
        }
        labels = {
            'is_hidden': 'Hidden Test (not visible to students)',
            'order': 'Display Order',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False
        self.fields['order'].required = False


class RuleSetForm(forms.ModelForm):
    """Form for configuring static analysis rules"""
    class Meta:
        model = RuleSet
        fields = ['required_functions', 'forbidden_keywords', 'requires_docstring', 'max_function_length']
        widgets = {
            'required_functions': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Comma-separated list of required functions (e.g., calculate, validate, process)',
            }),
            'forbidden_keywords': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Comma-separated list of forbidden keywords (e.g., eval, exec, __import__)',
            }),
            'requires_docstring': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'max_function_length': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'help_text': 'Maximum lines per function (0 = no limit)',
            }),
        }
        labels = {
            'required_functions': 'Required Functions',
            'forbidden_keywords': 'Forbidden Keywords',
            'requires_docstring': 'Require docstrings on all functions',
            'max_function_length': 'Maximum Function Length (lines)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['required_functions'].required = False
        self.fields['forbidden_keywords'].required = False
        self.fields['max_function_length'].required = False

    def clean_required_functions(self):
        data = self.cleaned_data.get('required_functions', '').strip()
        if data and not all(func.strip().isidentifier() for func in data.split(',') if func.strip()):
            raise forms.ValidationError('Each function name must be a valid Python identifier')
        return data

    def clean_forbidden_keywords(self):
        data = self.cleaned_data.get('forbidden_keywords', '').strip()
        return data

    def clean_max_function_length(self):
        data = self.cleaned_data.get('max_function_length')
        if data is not None and data < 0:
            raise forms.ValidationError('Maximum function length must be 0 or greater')
        return data
