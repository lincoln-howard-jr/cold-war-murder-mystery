on run argv
  if (count of argv) < 1 then
    error "Usage: osascript txt_to_pages_character_brief.applescript <input.txt> [output.pages]"
  end if

  set inPath to my resolveInputPath(item 1 of argv)
  set outPath to my resolveOutputPath(argv, inPath)
  set briefText to my readTextFile(inPath)
  set parsed to my parseBriefText(briefText, inPath)

  set briefName to item 1 of parsed
  set backstoryText to item 2 of parsed
  set objectiveText to item 3 of parsed
  set connectionsText to item 4 of parsed

  set outputBody to my buildOutputText(briefName, backstoryText, objectiveText, connectionsText)
  do shell script "/bin/rm -rf " & quoted form of outPath
  my createPagesDocument(outputBody, outPath)
end run

on resolveInputPath(rawPath)
  set inPath to my absolutizePath(rawPath as text)
  do shell script "/bin/test -f " & quoted form of inPath
  return inPath
end resolveInputPath

on resolveOutputPath(argv, inPath)
  if (count of argv) >= 2 then
    set rawOutPath to item 2 of argv as text
  else
    set rawOutPath to my replaceExtension(inPath, ".pages")
  end if

  if rawOutPath does not end with ".pages" then set rawOutPath to rawOutPath & ".pages"
  return my absolutizePath(rawOutPath)
end resolveOutputPath

on readTextFile(inPath)
  return do shell script "/bin/cat " & quoted form of inPath
end readTextFile

on createPagesDocument(outputBody, outPath)
  set lastErr to "unknown error"

  repeat 4 times
    try
      with timeout of 600 seconds
        tell application "Pages"
          launch
          activate
        end tell
        delay 0.7

        tell application "Pages"
          set d to make new document
          delay 0.4
          set body text of d to outputBody
          delay 0.2
          my applyStandardFormatting(d)
          save d in (POSIX file outPath)
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

  error "Failed to create Pages document after retries: " & lastErr
end createPagesDocument

on parseBriefText(rawText, inPath)
  set normalized to my normalizeNewlines(rawText)
  set allLines to paragraphs of normalized

  set briefName to ""
  set backstoryLines to {}
  set objectiveLines to {}
  set connectionsLines to {}
  set currentSection to ""

  repeat with i from 1 to count of allLines
    set rawLine to item i of allLines as text
    set lineTrim to my trimText(rawLine)
    set lowerTrim to my lowercase(lineTrim)

    if my startsWith(lowerTrim, "character brief:") then
      if (length of lineTrim) > 16 then
        set briefName to my trimText(text 17 thru -1 of lineTrim)
      end if
      set currentSection to ""
    else if lowerTrim is "backstory" then
      set currentSection to "backstory"
    else if lowerTrim is "objective" then
      set currentSection to "objective"
    else if lowerTrim is "connections" then
      set currentSection to "connections"
    else
      if currentSection is "backstory" then
        set end of backstoryLines to rawLine
      else if currentSection is "objective" then
        set end of objectiveLines to rawLine
      else if currentSection is "connections" then
        set end of connectionsLines to rawLine
      end if
    end if
  end repeat

  if briefName is "" then set briefName to my filenameStem(inPath)

  set backstoryText to my trimBlankEdges(my joinLines(backstoryLines))
  set objectiveText to my trimBlankEdges(my joinLines(objectiveLines))
  set connectionsText to my trimBlankEdges(my joinLines(connectionsLines))

  return {briefName, backstoryText, objectiveText, connectionsText}
end parseBriefText

on buildOutputText(briefName, backstoryText, objectiveText, connectionsText)
  set blocks to {"Character Brief: " & briefName, "", "Backstory", backstoryText, "", "Objective", objectiveText, "", "Connections", connectionsText}
  return my joinLines(blocks)
end buildOutputText

on applyStandardFormatting(d)
  tell application "Pages"
    try
      set font of body text of d to "Menlo"
    on error
      try
        set font of body text of d to "Menlo-Regular"
      on error
        set font of body text of d to "Courier"
      end try
    end try
    set size of body text of d to 12
    set color of body text of d to {0, 0, 0}

    set pCount to count of paragraphs of body text of d
    repeat with i from 1 to pCount
      set pTextTrim to my trimText(paragraph i of body text of d as text)
      ignoring case
        if pTextTrim starts with "character brief:" then
          my styleParagraph(d, i, 16, true)
        else if pTextTrim is "backstory" or pTextTrim is "objective" or pTextTrim is "connections" then
          my styleParagraph(d, i, 13, true)
        end if
      end ignoring
    end repeat
  end tell
end applyStandardFormatting

on styleParagraph(d, idx, pSize, makeBold)
  tell application "Pages"
    if makeBold then
      try
        set font of paragraph idx of body text of d to "Menlo Bold"
      on error
        try
          set font of paragraph idx of body text of d to "Menlo-Bold"
        on error
          set font of paragraph idx of body text of d to "Courier-Bold"
        end try
      end try
    else
      try
        set font of paragraph idx of body text of d to "Menlo"
      on error
        try
          set font of paragraph idx of body text of d to "Menlo-Regular"
        on error
          set font of paragraph idx of body text of d to "Courier"
        end try
      end try
    end if
    set size of paragraph idx of body text of d to pSize
    set color of paragraph idx of body text of d to {0, 0, 0}
  end tell
end styleParagraph

on normalizeNewlines(t)
  set s to t as text
  set s to my replaceText(s, return & linefeed, return)
  set s to my replaceText(s, linefeed, return)
  return s
end normalizeNewlines

on joinLines(lineList)
  set AppleScript's text item delimiters to return
  set outText to lineList as text
  set AppleScript's text item delimiters to ""
  return outText
end joinLines

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

on trimText(t)
  return my trimBlankEdges(t as text)
end trimText

on replaceText(sourceText, findText, replaceWith)
  set AppleScript's text item delimiters to findText
  set parts to text items of sourceText
  set AppleScript's text item delimiters to replaceWith
  set outText to parts as text
  set AppleScript's text item delimiters to ""
  return outText
end replaceText

on startsWith(t, prefixText)
  if (length of t) < (length of prefixText) then return false
  return (text 1 thru (length of prefixText) of t) is prefixText
end startsWith

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
