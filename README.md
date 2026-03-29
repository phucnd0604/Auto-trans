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


key: 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