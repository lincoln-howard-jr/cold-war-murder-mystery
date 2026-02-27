on run argv
  if (count of argv) < 1 then error "Usage: osascript format_doc_in_pages.applescript <input.docx> [output.docx]"

  set inPath to POSIX path of (POSIX file (item 1 of argv))
  if (count of argv) >= 2 then
    set outPath to POSIX path of (POSIX file (item 2 of argv))
  else
    set outPath to inPath
  end if

  set tempOutPath to outPath
  if inPath is outPath then
    set tempBasePath to do shell script "/usr/bin/mktemp -t pagesfmt"
    set tempOutPath to tempBasePath & ".docx"
    do shell script "/bin/rm -f " & quoted form of tempOutPath
  end if

  with timeout of 600 seconds
    my debugLog("open:start " & inPath)
    set d to my openDocumentWithRetries(inPath)
    my debugLog("open:done")
    my waitForDocumentReady(d)
    my debugLog("ready:done")
    my debugLog("format:start")
    my applyStandardFormatting(d)
    my debugLog("format:done")

    tell application "Pages"
      my debugLog("export:start " & tempOutPath)
      export d to POSIX file tempOutPath as Microsoft Word
      my debugLog("export:done")
      my debugLog("close:start")
      close d saving no
      my debugLog("close:done")
      delay 0.3
    end tell
  end timeout

  if inPath is outPath then
    my debugLog("move:start")
    do shell script "/bin/mv -f " & quoted form of tempOutPath & " " & quoted form of inPath
    my debugLog("move:done")
  end if
end run

on openDocumentWithRetries(inPath)
  set lastErr to "unknown error"
  set targetStem to my filenameStem(inPath)

  repeat 8 times
    try
      my debugLog("open:attempt")
      tell application "Pages"
        launch
        try
          close every document saving no
        end try
      end tell
      delay 0.5

      do shell script "/usr/bin/open -b com.apple.Pages " & quoted form of inPath
      set d to my waitForTargetDocument(targetStem)
      return d
    on error errMsg number errNum
      set lastErr to ("(" & errNum & ") " & errMsg)
      my debugLog("open:error " & lastErr)
      try
        tell application "Pages"
          try
            close every document saving no
          end try
          quit
        end tell
      end try
      delay 2
    end try
  end repeat

  error "Failed to open document after retries: " & inPath & " " & lastErr
end openDocumentWithRetries

on waitForTargetDocument(targetStem)
  repeat 240 times
    try
      tell application "Pages"
        if (count of documents) > 0 then
          repeat with i from 1 to count of documents
            set d to document i
            try
              set docName to name of d
              if my nameMatchesStem(docName, targetStem) then return d
            end try
          end repeat

          -- If Pages opened a blank document instead, keep waiting briefly.
          -- The outer retry loop will reset Pages if the target never appears.
        end if
      end tell
    end try
    delay 0.25
  end repeat

  error "Timed out waiting for target document: " & targetStem
end waitForTargetDocument

on waitForDocumentReady(d)
  repeat 240 times
    try
      tell application "Pages"
        set pCount to count of paragraphs of body text of d
        if pCount > 0 then return
      end tell
    end try
    delay 0.25
  end repeat

  error "Document body text did not become ready"
end waitForDocumentReady

on applyStandardFormatting(d)
  tell application "Pages"
    try
      set font of body text of d to "Times New Roman"
    on error
      set font of body text of d to "TimesNewRomanPSMT"
    end try
    set size of body text of d to 12
    set color of body text of d to {0, 0, 0}

    set pCount to count of paragraphs of body text of d

    repeat with i from 1 to pCount
      set pTextTrim to my trimText(paragraph i of body text of d as text)
      if pTextTrim is not "" then
        my styleParagraph(d, i, 16, true)
        exit repeat
      end if
    end repeat

    repeat with i from 1 to pCount
      set pTextTrim to my trimText(paragraph i of body text of d as text)
      ignoring case
        if pTextTrim is "backstory" or pTextTrim is "objective" or pTextTrim is "connections" or pTextTrim is "overview" then
          my styleParagraph(d, i, 13, true)
        else if pTextTrim starts with "name:" or pTextTrim starts with "age:" or pTextTrim starts with "career:" or pTextTrim starts with "hometown:" or pTextTrim starts with "education:" then
          my styleParagraph(d, i, 12, true)
        end if
      end ignoring
    end repeat
  end tell
end applyStandardFormatting

on styleParagraph(d, idx, pSize, makeBold)
  tell application "Pages"
    if makeBold then
      try
        set font of paragraph idx of body text of d to "Times New Roman Bold"
      on error
        try
          set font of paragraph idx of body text of d to "TimesNewRomanPS-BoldMT"
        on error
          set font of paragraph idx of body text of d to "Times New Roman"
        end try
      end try
    else
      try
        set font of paragraph idx of body text of d to "Times New Roman"
      on error
        set font of paragraph idx of body text of d to "TimesNewRomanPSMT"
      end try
    end if
    set size of paragraph idx of body text of d to pSize
    set color of paragraph idx of body text of d to {0, 0, 0}
  end tell
end styleParagraph

on trimText(t)
  set s to t as text
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
end trimText

on debugLog(msg)
  try
    do shell script "/bin/echo " & quoted form of ((do shell script "date '+%H:%M:%S'") & " " & msg) & " >> /private/tmp/pages_format_debug.log"
  end try
end debugLog

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

on nameMatchesStem(docName, stem)
  set docStem to my filenameStem(docName as text)
  ignoring case
    if (docStem as text) is (stem as text) then return true
  end ignoring
  return false
end nameMatchesStem
