from setuptools import find_packages, setup

setup(
    name="cptools-web",
    version="0.1.0",
    packages=find_packages(),
    package_data={
        'cptools_web': [
            'resources/js/*.js',
            'resources/css/*.css',
            'resources/templates/*.j2',
        ],
    },
    include_package_data=True,
    install_requires=[
        "jinja2>=3.0",
    ],
)
