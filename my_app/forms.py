from django import forms


class UploadFileForm(forms.Form):
    file = forms.FileField(label='Upload Excel, CSV, or XML file')


DISTRIBUTION_CHOICES = [
    ('bernoulli', 'Bernoulli'),
    ('binomial', 'Binomial'),
    ('poisson', 'Poisson'),
    ('geometric', 'Geometric'),
    ('hypergeometric', 'Hypergeometric'),
    ('uniform', 'Uniform'),
    ('exponential', 'Exponential'),
    ('normal', 'Normal'),
]


class DistributionCalculatorForm(forms.Form):
    distribution_type = forms.ChoiceField(
        choices=DISTRIBUTION_CHOICES,
        label='Distribution Type'
    )

    n = forms.FloatField(required=False, label='n')
    p = forms.FloatField(required=False, label='p')
    k = forms.FloatField(required=False, label='k / x')
    lam = forms.FloatField(required=False, label='λ')
    a = forms.FloatField(required=False, label='a')
    b = forms.FloatField(required=False, label='b')
    mean = forms.FloatField(required=False, label='μ')
    sigma = forms.FloatField(required=False, label='σ')
    population_size = forms.FloatField(required=False, label='N')
    success_states = forms.FloatField(required=False, label='K')
    draws = forms.FloatField(required=False, label='r')


class ProblemSolverForm(forms.Form):
    problem_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 6}),
        label='Problem Text'
    )