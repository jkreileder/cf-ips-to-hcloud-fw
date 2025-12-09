# Contributing Guidelines

Thank you for considering contributing to this project!  We appreciate your time
and effort in making this project better.

To contribute to this project, please follow these guidelines:

## Issue Reporting

If you encounter any issues or have any feature requests, please open an issue
on the [issue
tracker](https://github.com/jkreileder/cf-ips-to-hcloud-fw/issues). Please
provide as much detail as possible, including steps to reproduce the issue.

## Development Setup

To set up your development environment:

1. Clone your fork of the repository
2. Run `make venv` to create a virtual environment and install dependencies (requires `uv`)
3. Install pre-commit hooks: `pre-commit install` or `prek install`
4. Run `make` to lint, test, and build the project

## Pull Requests

We welcome pull requests from the community.  Before submitting a pull request,
please make sure to:

1. Fork the repository and create a new branch for your changes.
2. Ensure that your code follows the project's coding style and conventions by running `make lint`.
3. Write tests for your changes; we maintain at least 80% code coverage.
4. Run `make test` to verify your changes don't break existing functionality.
5. Write clear and concise commit messages.
6. Commit messages should follow the [Conventional
   Commits](https://www.conventionalcommits.org/en/v1.0.0/) style: `<type>[optional scope]:
   <description>`. For example:
   - `feat: add new feature`
   - `fix(auth): resolve login issue`
   - `docs(contributing): update guidelines`
7. Sign your commits with `git commit -s` and ensure they are cryptographically signed (GPG/SSH).
8. Update the documentation and CHANGELOG if necessary.
9. Ensure all pre-commit hooks pass before pushing.

## Code of Conduct

Please note that this project follows a [Code of
Conduct](https://github.com/jkreileder/cf-ips-to-hcloud-fw/blob/main/.github/CODE_OF_CONDUCT.md).
By participating in this project, you agree to abide by its terms.

## License

By contributing to this project, you agree that your contributions will be
licensed under the [MIT
License](https://github.com/jkreileder/cf-ips-to-hcloud-fw/blob/main/LICENSE).

## Contact

If you have any questions or need further assistance, please contact the project
maintainers at [jk@blackdown.de](mailto:jk@blackdown.de).

We appreciate your contributions and look forward to your involvement in this
project!
