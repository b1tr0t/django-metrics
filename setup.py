from distutils.core import setup

setup(
    name='django-metrics',
    version=__import__('mailer').__version__,
    description='A reusable Django helper for making google chart datasets',
    long_description=open('README').read(),
    author='Peter McLachlan',
    author_email='peter@mobify.me',
    url='http://github.com/b1tr0t/django-metrics/tree/master',
    packages=[
        'metrics',
    ],
    package_dir={'metrics': 'metrics'},
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Framework :: Django',
    ]
)
