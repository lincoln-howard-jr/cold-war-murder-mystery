on run argv
  if (count of argv) < 1 then
    error "Usage: osascript pages_to_pdf_character_brief.applescript <input.pages|input_dir> [output.pdf|output_dir]"
  end if

  set inputPath to my resolveInputPath(item 1 of argv)

  if my isDirectory(inputPath) then
    set outputDir to my resolveOutputDir(argv, inputPath)
    set pageFiles to my listPagesFiles(inputPath)
    if (count of pageFiles) is 0 then
      error "No .pages files found in: " & inputPath
    end if

    repeat with inPath in pageFiles
      set outPath to outputDir & "/" & my filenameStem(inPath as text) & ".pdf"
      my ensureParentDirectory(outPath)
      my exportPagesToPDF(inPath as text, outPath)
    end repeat

    return "Converted " & (count of pageFiles) & " file(s) to " & outputDir
  else
    set outPath to my resolveSingleOutputPath(argv, inputPath)
    my ensureParentDirectory(outPath)
    my exportPagesToPDF(inputPath, outPath)
    return outPath
  end if
end run

on resolveInputPath(rawPath)
  set inPath to my absolutizePath(rawPath as text)
  try
    do shell script "/bin/test -e " & quoted form of inPath
  on error
    error "Input path not found: " & inPath
  end try
  return inPath
end resolveInputPath

on resolveOutputDir(argv, inputDir)
  if (count of argv) >= 2 then
    set outDir to my absolutizePath(item 2 of argv as text)
  else
    set outDir to inputDir
  end if

  do shell script "/bin/mkdir -p " & quoted form of outDir
  return outDir
end resolveOutputDir

on resolveSingleOutputPath(argv, inputPath)
  if (count of argv) < 2 then
    return my replaceExtension(inputPath, ".pdf")
  end if

  set rawOutPath to my absolutizePath(item 2 of argv as text)
  if my endsWith(my lowercase(rawOutPath), ".pdf") then
    return rawOutPath
  end if

  do shell script "/bin/mkdir -p " & quoted form of rawOutPath
  return rawOutPath & "/" & my filenameStem(inputPath) & ".pdf"
end resolveSingleOutputPath

on listPagesFiles(inputDir)
  set cmd to "/usr/bin/find " & quoted form of inputDir & " -maxdepth 1 \\( -type f -o -type d \\) -name '*.pages' -print | /usr/bin/sort"
  set rawList to do shell script cmd
  if rawList is "" then return {}
  return paragraphs of rawList
end listPagesFiles

on exportPagesToPDF(inPath, outPath)
  set lastErr to "unknown error"

  repeat 4 times
    try
      with timeout of 600 seconds
        tell application "Pages"
          launch
          activate
          set d to open (POSIX file inPath)
          delay 0.3
          my removePathIfExists(outPath)
          export d to (POSIX file outPath) as PDF
          close d saving no
        end tell
      end timeout
      return
    on error errMsg number errNum
      set lastErr to "(" & errNum & ") " & errMsg
      try
        tell application "Pages"
          try
            close every document saving no
          end try
        end tell
      end try
      delay 1
    end try
  end repeat

  error "Failed to export PDF after retries: " & lastErr & " | input=" & inPath
end exportPagesToPDF

on removePathIfExists(p)
  do shell script "/bin/rm -f " & quoted form of p
end removePathIfExists

on ensureParentDirectory(p)
  set parentPath to do shell script "/usr/bin/dirname " & quoted form of p
  do shell script "/bin/mkdir -p " & quoted form of parentPath
end ensureParentDirectory

on isDirectory(p)
  try
    do shell script "/bin/test -d " & quoted form of p
    return true
  on error
    return false
  end try
end isDirectory

on endsWith(t, suffixText)
  if (length of t) < (length of suffixText) then return false
  return (text ((length of t) - (length of suffixText) + 1) thru -1 of t) is suffixText
end endsWith

on lowercase(t)
  do shell script "/bin/echo " & quoted form of (t as text) & " | /usr/bin/tr '[:upper:]' '[:lower:]'"
end lowercase

on replaceExtension(p, newExt)
  set stem to my filenameStem(p)
  set AppleScript's text item delimiters to "/"
  set pathParts to text items of p
  set leafCount to count of pathParts
  if leafCount > 1 then
    set dirParts to items 1 thru (leafCount - 1) of pathParts
    set AppleScript's text item delimiters to "/"
    set dirPath to dirParts as text
    set AppleScript's text item delimiters to ""
    return dirPath & "/" & stem & newExt
  else
    set AppleScript's text item delimiters to ""
    return stem & newExt
  end if
end replaceExtension

on absolutizePath(rawPath)
  set p to my trimText(rawPath as text)
  if p is "" then error "Path cannot be empty"

  if p is "~" then
    set p to POSIX path of (path to home folder)
  else if my startsWith(p, "~/") then
    set homePath to POSIX path of (path to home folder)
    if homePath ends with "/" then
      set p to homePath & text 3 thru -1 of p
    else
      set p to homePath & "/" & text 3 thru -1 of p
    end if
  else if character 1 of p is not "/" then
    set cwdPath to do shell script "/bin/pwd"
    if cwdPath ends with "/" then
      set p to cwdPath & p
    else
      set p to cwdPath & "/" & p
    end if
  end if

  return p
end absolutizePath

on startsWith(t, prefixText)
  if (length of t) < (length of prefixText) then return false
  return (text 1 thru (length of prefixText) of t) is prefixText
end startsWith

on trimText(t)
  return my trimBlankEdges(t as text)
end trimText

on trimBlankEdges(t)
  set s to my normalizeNewlines(t)
  set ws to {space, return, linefeed, tab, character id 8232, character id 8233}

  repeat while s is not ""
    if (character 1 of s) is in ws then
      if (length of s) is 1 then return ""
      set s to text 2 thru -1 of s
    else
      exit repeat
    end if
  end repeat

  repeat while s is not ""
    if (character -1 of s) is in ws then
      if (length of s) is 1 then return ""
      set s to text 1 thru -2 of s
    else
      exit repeat
    end if
  end repeat

  return s
end trimBlankEdges

on normalizeNewlines(t)
  set s to t as text
  set s to my replaceText(s, return & linefeed, return)
  set s to my replaceText(s, linefeed, return)
  return s
end normalizeNewlines

on replaceText(sourceText, findText, replaceWith)
  set AppleScript's text item delimiters to findText
  set parts to text items of sourceText
  set AppleScript's text item delimiters to replaceWith
  set outText to parts as text
  set AppleScript's text item delimiters to ""
  return outText
end replaceText

on filenameStem(p)
  set t to p as text
  set AppleScript's text item delimiters to "/"
  set leaf to last text item of t
  set AppleScript's text item delimiters to "."
  if (count of text items of leaf) > 1 then
    set stem to (items 1 thru -2 of text items of leaf) as text
  else
    set stem to leaf
  end if
  set AppleScript's text item delimiters to ""
  return stem
end filenameStem
