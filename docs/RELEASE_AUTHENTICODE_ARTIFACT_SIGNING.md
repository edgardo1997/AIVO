# Sentinel 1.0.0: firma comercial con Microsoft Artifact Signing

La release comercial requiere **Public Trust**. No se acepta un certificado
autofirmado ni un perfil de prueba. El certificado privado permanece en
Microsoft Artifact Signing; no se almacena en el repositorio ni en el equipo.

## Precondiciones

- SignTool x64: `C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe`.
- .NET 8 Runtime x64 y `Azure.CodeSigning.Dlib.dll` x64 del cliente de
  Microsoft Artifact Signing.
- Un perfil Public Trust activo y una identidad con el rol
  `Artifact Signing Certificate Profile Signer`.
- Un `metadata.json` externo al repositorio, con `Endpoint`,
  `CodeSigningAccountName` y `CertificateProfileName` correspondientes a la
  misma región.

Ejecutar, desde la raíz del repositorio y después de autenticar la identidad
autorizada en Azure:

```powershell
.\scripts\sign-release-authenticode.ps1 `
  -ArtifactSigningMetadata 'C:\secure\artifact-signing-metadata.json' `
  -DlibPath 'C:\secure\Microsoft.ArtifactSigning.Client\bin\x64\Azure.CodeSigning.Dlib.dll'
```

El script firma exclusivamente los dos binarios 1.0.0 cuyos hashes previos
coinciden con el candidato validado, aplica timestamp SHA-256 de Microsoft y
verifica cada firma con `signtool verify /pa /v` y
`Get-AuthenticodeSignature`.

## Orden obligatorio después de Authenticode

1. Firmar Authenticode y aplicar timestamp.
2. Verificar ambas firmas con SignTool y PowerShell.
3. Regenerar los `.sig` de Tauri usando la clave privada de updater en el
   entorno seguro: Authenticode cambió los binarios y las firmas anteriores
   dejan de ser válidas.
4. Recalcular SHA-256.
5. Regenerar SBOM, manifiesto y checksums seleccionando solo MSI, MSI `.sig`,
   NSIS y NSIS `.sig` de Sentinel 1.0.0.
6. Generar `update.json` con las URLs finales de los artefactos firmados y la
   firma Tauri correspondiente; no publicarlo aún.
7. Ejecutar instalación limpia de MSI y NSIS, inicio, sidecar, UI, cierre,
   desinstalación y una prueba real del updater.
8. Publicar únicamente si Authenticode y el updater validan de forma simultánea.
