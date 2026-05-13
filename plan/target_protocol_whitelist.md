# Phase 0 Target Protocol Whitelist

**Version:** `protocol-whitelist.v1`  
**Chain:** Ethereum Mainnet (`chain_id=1`)  
**Freeze date:** 2026-05-13

This whitelist is the only Phase 1 source for protocol role tagging and
protocol-specific hot-path parsing.

## Sources Checked

- Uniswap v3 Ethereum deployment list:
  https://gov.uniswap.org/t/official-uniswap-v3-deployments-list/24323/2
- Uniswap v3 audits:
  https://developers.uniswap.org/docs/protocols/v3/audits
- Aave v3 Ethereum deployment note and address book pointer:
  https://governance.aave.com/t/bgd-aave-v3-ethereum-new-deployment-vs-aave-v2-upgrade/9990?page=2
- Aave v3 core audits and formal verification:
  https://github.com/aave/aave-v3-core
- Compound III docs:
  https://docs.compound.finance/
- Compound III OpenZeppelin audit:
  https://www.openzeppelin.com/news/compound-iii-audit
- Compound III ChainSecurity audit:
  https://www.chainsecurity.com/security-audit/compound-iii
- Chainlink ETH/USD feed:
  https://data.chain.link/feeds/ethereum/mainnet/eth-usd
- Chainlink USDC/USD feed:
  https://data.chain.link/feeds/ethereum/mainnet/usdc-usd
- Chainlink security and certification overview:
  https://chain.link/security

## Whitelisted Contracts

| protocol_id | Category | Contract | Address | Role | pause / guardian / emergency permissions | Docs / audit links |
|---|---|---|---|---|---|---|
| `uniswap_v3` | AMM / DEX | UniswapV3Factory | `0x1F98431c8aD98523631AE4a59f267346ea31F984` | factory / pool registry | No emergency pause for pool trading in Phase 0 assumptions; governance-controlled protocol parameters are not treated as incident response controls. | https://docs.uniswap.org/contracts/v3/overview |
| `uniswap_v3` | AMM / DEX | NonfungiblePositionManager | `0xC36442b4a4522E871399CD717aBDD847Ab11FE88` | LP position manager | No Phase 0 emergency action target. | https://docs.uniswap.org/contracts/v3/reference/periphery/NonfungiblePositionManager |
| `uniswap_v3_router` | Router / Aggregator | UniversalRouter | `0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD` | swap routing entrypoint | No Phase 0 emergency action target. | https://docs.uniswap.org/contracts/universal-router/overview |
| `uniswap_v3_router` | Router / Aggregator | SwapRouter02 | `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45` | swap routing entrypoint | No Phase 0 emergency action target. | https://docs.uniswap.org/contracts/v3/reference/periphery/SwapRouter |
| `aave_v3_ethereum` | Lending market | PoolAddressesProvider | `0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e` | address registry | Governance-controlled address provider; not directly used for automatic action. | https://aave.com/docs/developers/smart-contracts/pool-addresses-provider |
| `aave_v3_ethereum` | Lending market | Pool | `0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2` | lending pool entrypoint | Emergency pause/config changes must go through Aave governance, emergency admin, multisig, or delegated owner process. | https://aave.com/docs/developers/smart-contracts/pool |
| `aave_v3_ethereum` | Lending market | PoolConfigurator | `0x64b761D848206f447Fe2dd461b0c635Ec39EbB27` | reserve configuration / pause surface | Potential emergency surface; Phase 0 allows suggested transaction generation only after approval. | https://aave.com/docs/developers/smart-contracts/pool-configurator |
| `compound_v3_usdc` | Lending market | cUSDCv3 / Comet proxy | `0xc3d688B66703497DAA19211EEdff47f25384cdc3` | USDC base market | Pause guardian / governance controlled; Phase 0 allows suggested transaction generation only after approval. | https://docs.compound.finance/ |
| `chainlink_eth_usd` | Oracle | ETH/USD Feed Proxy | `0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419` | reference price feed | Chainlink-operated oracle surface; this project monitors and escalates, but does not control feed operation. | https://data.chain.link/feeds/ethereum/mainnet/eth-usd |
| `chainlink_usdc_usd` | Oracle | USDC/USD Feed Proxy | `0x8fFfFfd4AfB6115b954Bd326cbe7B4BA576818f6` | reference price feed | Chainlink-operated oracle surface; this project monitors and escalates, but does not control feed operation. | https://data.chain.link/feeds/ethereum/mainnet/usdc-usd |

## Pool-Level Expansion Rule

Uniswap v3 pool contracts are not listed exhaustively in Phase 0. Phase 1 may
derive pool addresses by calling `UniswapV3Factory.getPool(token0, token1, fee)`
for approved token pairs. Each derived pool must inherit:

- `protocol_id=uniswap_v3`
- `contract_role=pool`
- source reference to the factory call result
- token pair and fee tier
- first-seen block

## Change Control

New protocols or contracts require:

1. protocol owner and category;
2. mainnet contract address;
3. role assignment;
4. emergency authority review;
5. docs and audit/source links;
6. reviewer sign-off in this file.

## Protocol Documentation and Audit References

| protocol_id | Documentation | Audit / security reference |
|---|---|---|
| `uniswap_v3` | https://docs.uniswap.org/contracts/v3/overview | https://developers.uniswap.org/docs/protocols/v3/audits |
| `uniswap_v3_router` | https://docs.uniswap.org/contracts/universal-router/overview | https://developers.uniswap.org/docs/protocols/v3/audits |
| `aave_v3_ethereum` | https://aave.com/docs/developers/smart-contracts/pool | https://github.com/aave/aave-v3-core |
| `compound_v3_usdc` | https://docs.compound.finance/ | https://www.openzeppelin.com/news/compound-iii-audit and https://www.chainsecurity.com/security-audit/compound-iii |
| `chainlink_eth_usd` | https://data.chain.link/feeds/ethereum/mainnet/eth-usd | https://chain.link/security |
| `chainlink_usdc_usd` | https://data.chain.link/feeds/ethereum/mainnet/usdc-usd | https://chain.link/security |
