# AutoTrans

## Tao File Share

Chay:

```powershell
.\release_share.ps1
```

Neu muon bo qua test:

```powershell
.\release_share.ps1 -SkipTests
```

File ket qua:

```text
dist\AutoTrans-shareable.zip
```

## Chay App Tu File Share

1. Giai nen `AutoTrans-shareable.zip`
2. Chay:

```powershell
.\bootstrap_portable.ps1
```

Neu muon ban nhe hon:

```powershell
.\bootstrap_portable.ps1 -Profile lite
```

3. Mo app:

```text
run_portable.cmd
```
