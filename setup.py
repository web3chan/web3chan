from setuptools import setup

__version__ = "1.0.0"

with open("README.md", "r") as f:
    long_description = f.read()

setup(
    name='web3chan',
    version=__version__,
    description='like 4chan, but in web3',
    long_description_content_type='text/markdown',
    long_description=long_description,
    packages=['web3chan'],
    install_requires=[
        'aroma',
        'databases',
        'orm',
        'httpx',
        'websockets',
        'orjson'
    ],
    url='https://github.com/web3chan/web3chan',
    author='zhoreeq',
    author_email='zhoreeq@protonmail.com',
    keywords='mastodon api asyncio',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Communications',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Programming Language :: Python :: 3',
    ]
)
