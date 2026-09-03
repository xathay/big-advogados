# Segurança

## Versões suportadas

Somente a versão mais recente publicada no repositório oficial recebe
correções de segurança. Forks e pacotes de terceiros podem conservar código
antigo e não são considerados distribuições oficiais do Big Advogados.

Repositório oficial: <https://github.com/xathay/big-advogados>

## Relato responsável

Falhas de segurança devem ser comunicadas pelo recurso privado **Security
Advisories** do repositório:

<https://github.com/xathay/big-advogados/security/advisories/new>

Não publique em uma issue dados de certificados, documentos, nomes de partes,
números de processos, caminhos locais, logs integrais, senhas, PINs, tokens ou
chaves. Use exemplos sintéticos e remova metadados antes de anexar arquivos.

## Limites da validação

- A validação local do PDF confirma a integridade criptográfica da assinatura.
- A confiança da cadeia ICP-Brasil e o estado de revogação devem ser conferidos
  por serviço oficial ou ferramenta apropriada ao caso concreto.
- A integração VidaaS por API REST permanece desabilitada até existir contrato
  técnico oficial e cobertura de testes. O caminho PKCS#11 local é independente.

## Publicação

Antes de cada release, devem ser conferidos o diff, os arquivos não rastreados,
as capturas de tela e os metadados dos artefatos. Nenhum certificado PFX/P12,
chave privada, documento jurídico, log de produção ou configuração pessoal deve
integrar o repositório ou o pacote distribuído.

Pacotes Arch destinados à publicação devem ser gerados em **clean chroot** com
caminho neutro. O `.BUILDINFO` registra o diretório de compilação e o inventário
de pacotes do ambiente; artefatos produzidos diretamente na estação de trabalho
são exclusivamente locais e não devem ser anexados a releases.
