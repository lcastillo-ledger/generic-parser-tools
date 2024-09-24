const fs = require('fs');
const abiDecoder = require('abi-decoder');
const yargs = require('yargs');
const Argv = require('yargs');
const web3 = require('web3');



// Function to handle parameter types, including structs
function signatureParam(param) {
    if (param.type === 'tuple') {
        const componentTypes = param.components.map(signatureParam).join(',');
        return `(${componentTypes})`;
    } else if (param.type === 'tuple[]') {
        const componentTypes = param.components.map(signatureParam).join(',');
        return `(${componentTypes})[]`;
    } else {
        return param.type;
    }
}

function declarationParam(param) {
    if (param.type === 'tuple' || param.type === 'tuple[]') {
        let internalType = param.internalType;
        if (internalType.startsWith('struct ')) {
            internalType = internalType.replace(/^struct \w+\./, '');
        }
        return `${internalType} ${param.name}`;
    } else {
        return `${param.type} ${param.name}`;    
    }
}

// Function to reconstruct function signature
function reconstructFunctionSignature(abiItem, paramTransform) {
    if (abiItem.type === 'function') {
        const functionName = abiItem.name;
        const paramTypes = abiItem.inputs.map(paramTransform).join(',');
        return `${functionName}(${paramTypes})`;
    }
    return null;
}

function listFunction(abiFunctionItem) {
    selector = web3.eth.abi.encodeFunctionSignature(abiFunctionItem);
    signature = reconstructFunctionSignature(abiFunctionItem, signatureParam);
    declaration = reconstructFunctionSignature(abiFunctionItem, declarationParam);
    return `Function:
    Name: ${abiFunctionItem.name}
    Selector: ${selector}
    Signature: ${signature}
    Declaration: ${declaration}
    `;
}

const list_functions = (Argv) => {
    const abiFilePath = Argv.a;
    const abiJson = JSON.parse(fs.readFileSync(abiFilePath, 'utf8'));

    const functionSignatures = abiJson
        .filter(item => item.type === 'function')
        .map(listFunction)
        .filter(item => item !== null);

    console.log(functionSignatures.join('\n'));
}

const decode_tx = (Argv) => {
    const abiFilePath = Argv.a;
    const txInputFilePath = Argv.t;

    const abiJson = JSON.parse(fs.readFileSync(abiFilePath, 'utf8'));
    const rawTxInput = fs.readFileSync(txInputFilePath, 'utf8').trim();

    abiDecoder.addABI(abiJson);
    const decodedData = abiDecoder.decodeMethod(rawTxInput);

    console.log(JSON.stringify(decodedData, null, 2));
}

const encode_tx = (Argv) => {
    const abiFilePath = Argv.a;
    const functionName = Argv.f;
    const functionParams = JSON.parse(Argv.p);

    const abiJson = JSON.parse(fs.readFileSync(abiFilePath, 'utf8'));
    const abiFunction = abiJson.find(item => item.name === functionName);

    encoded_parameters = web3.eth.abi.encodeFunctionCall(abiFunction, functionParams);

    const selector = encoded_parameters.slice(0, 10);
    const params = encoded_parameters.slice(10).match(/.{1,64}/g);

    if (Argv.x) {
        console.log(encoded_parameters);
    } else
    {
        console.log(`Selector: ${selector}`);
        console.log('Chunks:');
        params.forEach((param, index) => {
            console.log(`Chunk ${String(index).padStart(3, ' ')}: ${param}`);
        });
    }
}

const get_abi = (argv) => {
    abi_url = `https://api.etherscan.io/api?module=contract&action=getabi&address=${argv.address}&tag=latest&apikey=${argv.key}`;

    axios.get(abi_url)
        .then(response => {
            if (response.data.status === '1') {
                json_response = JSON.parse(response.data.result);
                console.log(JSON.stringify(json_response, null, 4));
            } else {
                console.error(`Error: ${response.data.message}`);
            }
        })
        .catch(error => {
            console.error(`Error: ${error.message}`);
        });
};

const get_txinput = (argv) => {
    tx_input_url = `https://api.etherscan.io/api?module=proxy&action=eth_getTransactionByHash&txhash=${argv.hash}&apikey=${argv.key}`;

    axios.get(tx_input_url)
        .then(response => {
            console.log(`${response.data.result.input}`);
        })
        .catch(error => {
            console.error(`Error: ${error}`);
        });
};

const argv = yargs
    .scriptName("abitool")
    .command('decode', 'Decode a transaction input', (yargs) => {
        return yargs
        .option('tx', {
            alias: 't',
            description: 'Path to the tx raw input file',
            type: 'string',
            demandOption: true
        })
        .option('abi', {
            alias: 'a',
            description: 'Path to the abi file',
            type: 'string',
            demandOption: true
        })
        }, decode_tx)
    .command('encode', 'Encode the parameters of a function call given parameters and abi', (yargs) => {
        return yargs
        .option('abi', {
            alias: 'a',
            description: 'Path to the abi file',
            type: 'string',
            demandOption: true
        })
        .option('function', {
            alias: 'f',
            description: 'Function name to encode',
            type: 'string',
            demandOption: true
        })
        .option('params', {
            alias: 'p',
            description: 'Function parameters to encode',
            type: 'string',
            demandOption: true
        })
        .option('hex', {
            alias: 'x',
            description: 'Encode as a single hx string',
            type: 'boolean'
        })
        }, encode_tx)
    .command('list', 'List functions contained in the abi', (yargs) => {
        return yargs
        .option('abi', {
            alias: 'a',
            description: 'Path to the abi file',
            type: 'string',
            demandOption: true
        })
        }, list_functions)
    .command('abi', 'Get the details of an abi', (yargs) => {
        return yargs
        .option('address', {
            alias: 'a',
            description: 'Ethereum address to query',
            type: 'string',
            demandOption: true
        })
        .option('key', {
            alias: 'k',
            description: 'API Key for Etherscan',
            type: 'string',
            demandOption: true
        })
        }, get_abi) 
    .command('txinput', 'Get the input data of a tx', (yargs) => {
        return yargs
        .option('hash', {
            alias: 'H',
            description: 'Tx hash to query',
            type: 'string',
            demandOption: true
        })
        .option('key', {
            alias: 'k',
            description: 'API Key for Etherscan',
            type: 'string',
            demandOption: true
        })
        }, get_txinput)
    .help()
    .alias('help', 'h')
    .parse();
