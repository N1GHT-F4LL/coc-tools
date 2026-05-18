$src='d:\coc-tools\coc_bot\assets'
$dst='d:\coc-tools\coc_bot\assets_v2\buildings'
$all=Get-ChildItem -Path $src -Recurse -File -Filter '*.png' -ErrorAction SilentlyContinue

$buckets=@{
  defenses=@('cannon','archer_tower','wizard_tower','air_defense','inferno','xbow','x_bow','eagle','scatter','bomb_tower','tesla','mortar','sweeper','monolith','ricochet','multi_archer','builder_hut')
  storages=@('gold_storage','elixir_storage','dark_elixir_storage','storage','treasury')
  resource_collectors=@('gold_mine','elixir_collector','dark_elixir_drill','collector','drill','mine_full')
  walls=@('wall')
  traps=@('bomb','spring','trap','skeleton_trap','tornado')
  utility=@('townhall','town_hall','clan_castle','army_camp','barracks','lab','workshop','spell_factory','pet_house','blacksmith','builder_base','capital_hall','forge','attack_criteria','target','trophy')
}

$copied=0
foreach($f in $all){
  $name=[IO.Path]::GetFileNameWithoutExtension($f.Name).ToLower().Replace(' ','_')
  $rel=$f.FullName.Substring($src.Length).ToLower()

  $bucket=$null
  foreach($k in $buckets.Keys){
    foreach($kw in $buckets[$k]){
      if($name -like "*$kw*" -or $rel -like "*$kw*") { $bucket=$k; break }
    }
    if($bucket){break}
  }
  if(-not $bucket){ continue }

  $outDir=Join-Path $dst $bucket
  New-Item -ItemType Directory -Path $outDir -Force | Out-Null

  $target=Join-Path $outDir ("$name.png")
  if(Test-Path -LiteralPath $target){
    $hash=(Get-FileHash -LiteralPath $f.FullName -Algorithm MD5).Hash.Substring(0,8).ToLower()
    $target=Join-Path $outDir ("{0}_{1}.png" -f $name,$hash)
    if(Test-Path -LiteralPath $target){ continue }
  }

  Copy-Item -LiteralPath $f.FullName -Destination $target -Force
  $copied++
}

Write-Output "COPIED=$copied"
Get-ChildItem -Path $dst -Directory | ForEach-Object {
  $c=(Get-ChildItem -Path $_.FullName -File | Measure-Object).Count
  Write-Output ("{0}`t{1}" -f $_.Name,$c)
}
