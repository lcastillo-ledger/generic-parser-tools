# generic-parser-tools

Various tools to help test path generation in the generic parser design

## path.dogma

The reference of the TLV encoding of a binary path used by the generic parser to encode a specific field value in the function's calldata

## abitool

Provide commands to manipulate ABIs and function calls in their solidity and json encodings
With an etherscan key, also allows retrieving ABIs and Tx input data directly

```
abitool [command]

Commands:
  abitool decode   Decode a transaction input
  abitool encode   Encode the parameters of a function call given parameters and
                   abi
  abitool list     List functions contained in the abi
  abitool abi      Get the details of an abi
  abitool txinput  Get the input data of a tx

Options:
      --version  Show version number                                   [boolean]
  -h, --help     Show help                                             [boolean]
```

## binary_path_gen.py

Python script to generate and test binary paths in an ABI, using the dogma binary specification


