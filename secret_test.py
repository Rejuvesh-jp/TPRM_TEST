from azure.identity import ManagedIdentityCredential
from azure.keyvault.secrets import SecretClient
import os

credential = ManagedIdentityCredential()

VAULT_URL =  "https://tprmaivault.vault.azure.net/"

client = SecretClient(
    vault_url=VAULT_URL,
    credential=credential
)

secret = client.get_secret("tmrpaisecrectnew")

print("isassessmemntuat1 == ", secret.value)
