import os
import math
import re
import xml.etree.ElementTree as ET

import matplotlib.pyplot as plt
import pandas as pd

from django.conf import settings
from django.shortcuts import render, redirect

from .forms import UploadFileForm, DistributionCalculatorForm, ProblemSolverForm


def factorial_safe(n):
    n = int(n)
    if n < 0:
        raise ValueError('Factorial is not defined for negative numbers.')
    return math.factorial(n)


def combination(n, r):
    n = int(n)
    r = int(r)
    if r < 0 or n < 0 or r > n:
        return 0
    return math.comb(n, r)


def normal_pdf(x, mu, sigma):
    return (1 / (sigma * math.sqrt(2 * math.pi))) * math.exp(-((x - mu) ** 2) / (2 * sigma ** 2))


def normal_cdf(x, mu, sigma):
    z = (x - mu) / (sigma * math.sqrt(2))
    return 0.5 * (1 + math.erf(z))


def categorize_time(hour):
    if pd.isna(hour):
        return 'Unknown'
    if 0 <= hour < 6:
        return '00-06'
    elif 6 <= hour < 12:
        return '06-12'
    elif 12 <= hour < 18:
        return '12-18'
    elif 18 <= hour < 24:
        return '18-24'
    return 'Unknown'


def clean_numeric_value(value):
    if pd.isna(value):
        return None

    value = str(value).strip()
    if value == '':
        return None

    value = value.replace(' ', '')
    value = value.replace(',', '.')

    try:
        return float(value)
    except ValueError:
        return None


def categorize_duration(x):
    value = clean_numeric_value(x)

    if value is None:
        return 'Unknown'
    if value <= 60:
        return '0-60'
    elif value <= 300:
        return '60-300'
    elif value <= 600:
        return '300-600'
    else:
        return '600+'


def parse_xml_to_dataframe(file_path):
    tree = ET.parse(file_path)
    root = tree.getroot()

    rows = []

    for elem in root.iter():
        children = list(elem)
        if children:
            row = {}
            simple_children = [child for child in children if len(list(child)) == 0]
            if len(simple_children) >= 2:
                for child in simple_children:
                    tag = child.tag.split('}')[-1]
                    text = child.text.strip() if child.text else ''
                    row[tag] = text
                if row:
                    rows.append(row)

    if rows:
        return pd.DataFrame(rows)

    try:
        return pd.read_xml(file_path)
    except Exception:
        raise ValueError('XML structure could not be parsed into tabular data')


def read_uploaded_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.csv':
        try:
            return pd.read_csv(file_path)
        except UnicodeDecodeError:
            return pd.read_csv(file_path, encoding='latin1')

    if ext == '.xlsx':
        return pd.read_excel(file_path, engine='openpyxl')

    if ext == '.xls':
        return pd.read_excel(file_path)

    if ext == '.xml':
        return parse_xml_to_dataframe(file_path)

    raise ValueError(f'Unsupported file format: {ext}')


def save_plot(fig, filename):
    media_root = settings.MEDIA_ROOT or os.path.join(settings.BASE_DIR, 'media')
    os.makedirs(media_root, exist_ok=True)

    path = os.path.join(media_root, filename)
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)

    return settings.MEDIA_URL + filename


def home(request):
    return render(request, 'my_app/home.html')


def upload_file(request):
    form = UploadFileForm()
    error = None

    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['file']

            media_root = settings.MEDIA_ROOT or os.path.join(settings.BASE_DIR, 'media')
            os.makedirs(media_root, exist_ok=True)

            file_path = os.path.join(media_root, uploaded_file.name)

            with open(file_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)

            request.session['file_path'] = file_path
            return redirect('mapping')

    return render(request, 'my_app/upload.html', {
        'form': form,
        'error': error
    })


def mapping(request):
    file_path = request.session.get('file_path')

    if not file_path:
        return redirect('upload_file')

    try:
        df = read_uploaded_file(file_path)
        df = df.dropna(axis=1, how='all')
        df = df.fillna('')
    except Exception as e:
        return render(request, 'my_app/upload.html', {
            'form': UploadFileForm(),
            'error': f'File could not be read: {str(e)}'
        })

    columns = df.columns.tolist()

    if request.method == 'POST':
        time_col = request.POST.get('time_col')
        duration_col = request.POST.get('duration_col')

        request.session['time_col'] = time_col
        request.session['duration_col'] = duration_col

        return redirect('result')

    return render(request, 'my_app/mapping.html', {
        'columns': columns
    })


def result_view(request):
    file_path = request.session.get('file_path')
    time_col = request.session.get('time_col')
    duration_col = request.session.get('duration_col')

    if not file_path or not time_col or not duration_col:
        return redirect('upload_file')

    try:
        df = read_uploaded_file(file_path)
    except Exception as e:
        return render(request, 'my_app/result.html', {
            'error': f'File could not be processed: {str(e)}'
        })

    df = df.copy()
    df = df.dropna(how='all')

    if time_col not in df.columns or duration_col not in df.columns:
        return render(request, 'my_app/result.html', {
            'error': 'Selected columns were not found in the uploaded file.'
        })

    df[time_col] = pd.to_datetime(df[time_col], errors='coerce', dayfirst=True)
    df['duration_numeric'] = df[duration_col].apply(clean_numeric_value)

    df = df[df[time_col].notna()].copy()

    df['hour'] = df[time_col].dt.hour
    df['time_interval'] = df['hour'].apply(categorize_time)
    df['duration_cat'] = df['duration_numeric'].apply(categorize_duration)

    time_order = ['00-06', '06-12', '12-18', '18-24']
    duration_order = ['0-60', '60-300', '300-600', '600+']

    df = df[df['time_interval'].isin(time_order)].copy()
    df = df[df['duration_cat'].isin(duration_order)].copy()

    if df.empty:
        return render(request, 'my_app/result.html', {
            'error': 'No valid records remained after cleaning the selected columns.'
        })

    joint = pd.crosstab(df['time_interval'], df['duration_cat'])
    joint = joint.reindex(index=time_order, columns=duration_order, fill_value=0)

    total = int(joint.values.sum())
    prob = joint / total

    px = prob.sum(axis=1)
    py = prob.sum(axis=0)

    time_map = {'00-06': 1, '06-12': 2, '12-18': 3, '18-24': 4}
    dur_map = {'0-60': 1, '60-300': 2, '300-600': 3, '600+': 4}

    ex = sum(time_map[i] * px[i] for i in px.index)
    ey = sum(dur_map[j] * py[j] for j in py.index)

    dx = sum(((time_map[i] - ex) ** 2) * px[i] for i in px.index)
    dy = sum(((dur_map[j] - ey) ** 2) * py[j] for j in py.index)

    sigma_x = math.sqrt(dx) if dx > 0 else 0
    sigma_y = math.sqrt(dy) if dy > 0 else 0

    cov = 0
    for i in prob.index:
        for j in prob.columns:
            cov += (time_map[i] - ex) * (dur_map[j] - ey) * prob.loc[i, j]

    corr = cov / (sigma_x * sigma_y) if sigma_x > 0 and sigma_y > 0 else 0

    if corr > 0:
        direction = 'Positive'
    elif corr < 0:
        direction = 'Negative'
    else:
        direction = 'No clear'

    abs_corr = abs(corr)
    if abs_corr < 0.3:
        strength = 'Weak'
    elif abs_corr < 0.7:
        strength = 'Moderate'
    else:
        strength = 'Strong'

    peak_time_interval = px.idxmax()
    peak_duration_interval = py.idxmax()

    summary_text = (
        f'The highest concentration of records is observed in the {peak_time_interval} interval, '
        f'while the dominant duration category is {peak_duration_interval}. '
        f'The calculated correlation coefficient indicates a {strength.lower()} '
        f'{direction.lower()} relationship between call time and call duration.'
    )

    validation_joint_sum = int(joint.values.sum())
    validation_prob_sum = round(float(prob.values.sum()), 6)
    validation_px_sum = round(float(px.sum()), 6)
    validation_py_sum = round(float(py.sum()), 6)

    fig1, ax1 = plt.subplots(figsize=(10, 6))
    joint.plot(kind='bar', stacked=True, ax=ax1)
    ax1.set_title('Call Distribution by Time Interval and Duration Category')
    ax1.set_xlabel('Time Interval')
    ax1.set_ylabel('Frequency')
    ax1.tick_params(axis='x', rotation=0)
    fig1.tight_layout()
    chart_url = save_plot(fig1, 'chart.png')

    fig2, ax2 = plt.subplots(figsize=(8, 5))
    heatmap = ax2.imshow(joint.values, aspect='auto')
    fig2.colorbar(heatmap, ax=ax2, label='Frequency')
    ax2.set_xticks(range(len(joint.columns)))
    ax2.set_xticklabels(joint.columns)
    ax2.set_yticks(range(len(joint.index)))
    ax2.set_yticklabels(joint.index)
    ax2.set_title('Joint Frequency Heatmap')
    ax2.set_xlabel('Duration Category')
    ax2.set_ylabel('Time Interval')
    fig2.tight_layout()
    heatmap_url = save_plot(fig2, 'heatmap.png')

    fig3, ax3 = plt.subplots(figsize=(8, 5))
    px.plot(kind='bar', ax=ax3)
    ax3.set_title('Marginal Distribution of X')
    ax3.set_xlabel('Time Interval')
    ax3.set_ylabel('Probability')
    ax3.tick_params(axis='x', rotation=0)
    fig3.tight_layout()
    px_chart_url = save_plot(fig3, 'px_chart.png')

    fig4, ax4 = plt.subplots(figsize=(8, 5))
    py.plot(kind='bar', ax=ax4)
    ax4.set_title('Marginal Distribution of Y')
    ax4.set_xlabel('Duration Category')
    ax4.set_ylabel('Probability')
    ax4.tick_params(axis='x', rotation=0)
    fig4.tight_layout()
    py_chart_url = save_plot(fig4, 'py_chart.png')

    joint_html = joint.to_html(classes='table table-hover align-middle custom-table', border=0)
    prob_html = prob.round(4).to_html(classes='table table-hover align-middle custom-table', border=0)

    px_items = [{'label': idx, 'value': round(val, 4)} for idx, val in px.items()]
    py_items = [{'label': idx, 'value': round(val, 4)} for idx, val in py.items()]

    context = {
        'time_col': time_col,
        'duration_col': duration_col,
        'total_records': total,
        'valid_records': len(df),
        'peak_time_interval': peak_time_interval,
        'peak_duration_interval': peak_duration_interval,
        'direction': direction,
        'strength': strength,
        'summary_text': summary_text,
        'table': joint_html,
        'prob_table': prob_html,
        'px_items': px_items,
        'py_items': py_items,
        'EX': round(ex, 4),
        'EY': round(ey, 4),
        'DX': round(dx, 4),
        'DY': round(dy, 4),
        'sigma_x': round(sigma_x, 4),
        'sigma_y': round(sigma_y, 4),
        'cov': round(cov, 4),
        'corr': round(corr, 4),
        'chart_url': chart_url,
        'heatmap_url': heatmap_url,
        'px_chart_url': px_chart_url,
        'py_chart_url': py_chart_url,
        'validation_joint_sum': validation_joint_sum,
        'validation_prob_sum': validation_prob_sum,
        'validation_px_sum': validation_px_sum,
        'validation_py_sum': validation_py_sum,
        'error': None,
    }

    return render(request, 'my_app/result.html', context)


def calculate_distribution(data):
    dist = data.get('distribution_type')

    if dist == 'bernoulli':
        p = float(data['p'])
        q = 1 - p
        mean = p
        variance = p * q
        result = {
            'name': 'Bernoulli Distribution',
            'formula': 'P(X=1)=p, P(X=0)=1-p',
            'values': {
                'P(X=1)': round(p, 6),
                'P(X=0)': round(q, 6),
                'Mean': round(mean, 6),
                'Variance': round(variance, 6),
            }
        }
        return result

    if dist == 'binomial':
        n = int(data['n'])
        p = float(data['p'])
        k = int(data['k'])
        q = 1 - p
        prob = combination(n, k) * (p ** k) * (q ** (n - k))
        mean = n * p
        variance = n * p * q
        result = {
            'name': 'Binomial Distribution',
            'formula': 'P(X=k)=C(n,k)p^k(1-p)^(n-k)',
            'values': {
                'P(X=k)': round(prob, 6),
                'Mean': round(mean, 6),
                'Variance': round(variance, 6),
            }
        }
        return result

    if dist == 'poisson':
        lam = float(data['lam'])
        k = int(data['k'])
        prob = (math.exp(-lam) * (lam ** k)) / factorial_safe(k)
        result = {
            'name': 'Poisson Distribution',
            'formula': 'P(X=k)=e^(-λ) λ^k / k!',
            'values': {
                'P(X=k)': round(prob, 6),
                'Mean': round(lam, 6),
                'Variance': round(lam, 6),
            }
        }
        return result

    if dist == 'geometric':
        p = float(data['p'])
        k = int(data['k'])
        prob = ((1 - p) ** (k - 1)) * p
        mean = 1 / p
        variance = (1 - p) / (p ** 2)
        result = {
            'name': 'Geometric Distribution',
            'formula': 'P(X=k)=(1-p)^(k-1)p',
            'values': {
                'P(X=k)': round(prob, 6),
                'Mean': round(mean, 6),
                'Variance': round(variance, 6),
            }
        }
        return result

    if dist == 'hypergeometric':
        N = int(data['population_size'])
        K = int(data['success_states'])
        r = int(data['draws'])
        k = int(data['k'])

        numerator = combination(K, k) * combination(N - K, r - k)
        denominator = combination(N, r)

        prob = numerator / denominator if denominator != 0 else 0

        mean = r * (K / N)
        variance = r * (K / N) * (1 - K / N) * ((N - r) / (N - 1)) if N > 1 else 0

        result = {
            'name': 'Hypergeometric Distribution',
            'formula': 'P(X=k) = [C(K,k)C(N-K,r-k)] / C(N,r)',
            'values': {
                'P(X=k)': round(prob, 6),
                'Mean': round(mean, 6),
                'Variance': round(variance, 6),
            }
        }
        return result

    if dist == 'uniform':
        a = float(data['a'])
        b = float(data['b'])
        x = float(data['k'])

        density = 1 / (b - a) if a <= x <= b and b != a else 0
        mean = (a + b) / 2
        variance = ((b - a) ** 2) / 12

        result = {
            'name': 'Uniform Distribution',
            'formula': 'f(x)=1/(b-a), a≤x≤b',
            'values': {
                'f(x)': round(density, 6),
                'Mean': round(mean, 6),
                'Variance': round(variance, 6),
            }
        }
        return result

    if dist == 'exponential':
        lam = float(data['lam'])
        x = float(data['k'])

        density = lam * math.exp(-lam * x) if x >= 0 else 0
        cdf = 1 - math.exp(-lam * x) if x >= 0 else 0
        mean = 1 / lam
        variance = 1 / (lam ** 2)

        result = {
            'name': 'Exponential Distribution',
            'formula': 'f(x)=λe^(-λx), x≥0',
            'values': {
                'f(x)': round(density, 6),
                'F(x)': round(cdf, 6),
                'Mean': round(mean, 6),
                'Variance': round(variance, 6),
            }
        }
        return result

    if dist == 'normal':
        mu = float(data['mean'])
        sigma = float(data['sigma'])
        x = float(data['k'])

        density = normal_pdf(x, mu, sigma)
        cdf = normal_cdf(x, mu, sigma)

        result = {
            'name': 'Normal Distribution',
            'formula': 'f(x)=(1/(σ√(2π)))e^(-(x-μ)^2/(2σ^2))',
            'values': {
                'f(x)': round(density, 6),
                'F(x)': round(cdf, 6),
                'Mean': round(mu, 6),
                'Variance': round(sigma ** 2, 6),
            }
        }
        return result

    raise ValueError('Unsupported distribution type')


def distribution_calculator(request):
    form = DistributionCalculatorForm()
    result = None
    error = None

    if request.method == 'POST':
        form = DistributionCalculatorForm(request.POST)
        if form.is_valid():
            try:
                result = calculate_distribution(form.cleaned_data)
            except Exception as e:
                error = str(e)

    return render(request, 'my_app/distribution_calculator.html', {
        'form': form,
        'result': result,
        'error': error,
    })


def solve_text_problem(text):
    lower = text.lower().strip()

    if 'binomial' in lower:
        n_match = re.search(r'n\s*=\s*(\d+)', lower)
        p_match = re.search(r'p\s*=\s*([0-9]*\.?[0-9]+)', lower)
        k_match = re.search(r'k\s*=\s*(\d+)', lower)

        if n_match and p_match and k_match:
            n = int(n_match.group(1))
            p = float(p_match.group(1))
            k = int(k_match.group(1))
            q = 1 - p
            prob = combination(n, k) * (p ** k) * (q ** (n - k))

            return {
                'detected_type': 'Binomial',
                'steps': [
                    f'Extracted parameters: n={n}, p={p}, k={k}',
                    'Using formula: P(X=k)=C(n,k)p^k(1-p)^(n-k)',
                    f'P(X={k}) = C({n},{k}) × {p}^{k} × {q}^{n-k}',
                    f'Final probability = {round(prob, 6)}',
                ],
                'final_answer': round(prob, 6),
            }

    if 'poisson' in lower:
        lam_match = re.search(r'(lambda|lam|λ)\s*=\s*([0-9]*\.?[0-9]+)', lower)
        k_match = re.search(r'k\s*=\s*(\d+)', lower)

        if lam_match and k_match:
            lam = float(lam_match.group(2))
            k = int(k_match.group(1))
            prob = (math.exp(-lam) * (lam ** k)) / factorial_safe(k)

            return {
                'detected_type': 'Poisson',
                'steps': [
                    f'Extracted parameters: λ={lam}, k={k}',
                    'Using formula: P(X=k)=e^(-λ) λ^k / k!',
                    f'Final probability = {round(prob, 6)}',
                ],
                'final_answer': round(prob, 6),
            }

    if 'bernoulli' in lower:
        p_match = re.search(r'p\s*=\s*([0-9]*\.?[0-9]+)', lower)
        if p_match:
            p = float(p_match.group(1))
            return {
                'detected_type': 'Bernoulli',
                'steps': [
                    f'Extracted parameter: p={p}',
                    'Bernoulli outcomes are 0 and 1.',
                    f'P(X=1)={p}, P(X=0)={round(1-p, 6)}',
                ],
                'final_answer': {
                    'P(X=1)': round(p, 6),
                    'P(X=0)': round(1 - p, 6),
                },
            }

    return {
        'detected_type': 'Unknown',
        'steps': [
            'The system could not confidently detect a supported distribution from the text.',
            'Supported MVP problem types: Bernoulli, Binomial, Poisson.',
            'Try writing the problem with explicit parameters such as n=10, p=0.4, k=3.',
        ],
        'final_answer': 'Detection failed',
    }


def problem_solver(request):
    form = ProblemSolverForm()
    solution = None

    if request.method == 'POST':
        form = ProblemSolverForm(request.POST)
        if form.is_valid():
            text = form.cleaned_data['problem_text']
            solution = solve_text_problem(text)

    return render(request, 'my_app/problem_solver.html', {
        'form': form,
        'solution': solution,
    })


TRAINER_DATA = {
    'joint-distribution': {
        'title': 'Joint Distribution',
        'theory': 'A joint distribution describes the probabilities of two random variables occurring together.',
        'example': 'Build n_ij, then divide each cell by n to obtain p_ij.',
        'quiz_question': 'What do you obtain after dividing each n_ij by total n?',
        'quiz_answer': 'Joint probability distribution p_ij',
    },
    'expectation-variance': {
        'title': 'Expectation and Variance',
        'theory': 'Expectation measures the average value, while variance measures spread around the mean.',
        'example': 'M[X]=Σx_iP(X=x_i), D[X]=Σ(x_i-M[X])²P(X=x_i).',
        'quiz_question': 'What does variance measure?',
        'quiz_answer': 'Spread around the mean',
    },
    'correlation': {
        'title': 'Covariance and Correlation',
        'theory': 'Covariance shows joint variation and correlation normalizes it to a -1 to 1 scale.',
        'example': 'r(X,Y)=Cov(X,Y)/(σ(X)σ(Y)).',
        'quiz_question': 'What range can correlation take?',
        'quiz_answer': 'From -1 to 1',
    },
}


def trainer_home(request):
    topics = [
        {'slug': slug, 'title': data['title']}
        for slug, data in TRAINER_DATA.items()
    ]

    return render(request, 'my_app/trainer_home.html', {
        'topics': topics
    })


def trainer_topic(request, topic_slug):
    topic = TRAINER_DATA.get(topic_slug)

    if not topic:
        return redirect('trainer_home')

    return render(request, 'my_app/trainer_topic.html', {
        'topic': topic
    })