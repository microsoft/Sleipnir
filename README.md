# Project

Sleipnir is a tool for randomizing software data types in python. It is designed to help aid design
verification of complex SoC designs. This repo contains the sleipnir tool and a set of examples.

# Paper
The paper describing the tool is published as part of DVCon 2025 proceedings. It is available at
{TBD}.

# Quick Start
To get started with sleipnir, clone the repo and install the requirements.

1. Clone the repo
```bash
git clone <repo_path>
```
2. Create a virtual environment
```bash
python3 -m venv sleipnir
```
3. Activate the virtual environment
```bash
source sleipnir/bin/activate
```
4. Install the requirements
```bash
pip install -r requirements.txt
```
5. Set the environment variable
```bash
export ELF_PATH=<path_to_sleipnir_repo>/build
```
6. Compile the C library with debug symbols
```bash
mkdir -p build
gcc -g lib/sleipnir.c -o build/frame.elf
```
7. Run the tool
```bash
cd build
python3 ../src/sleipnir.py ../test/input.yml output.yml
```
Outputs are saved in the `build` directory.

# Examples

## Contributing

This project welcomes contributions and suggestions.  Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit https://cla.opensource.microsoft.com.

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft 
trademarks or logos is subject to and must follow 
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
