$nssm = 'C:\nssm\nssm-2.24\win64\nssm.exe'
& $nssm get AgenticTraderAPI  AppStdout
& $nssm get AgenticTraderAPI  AppStderr
& $nssm get AgenticTraderAPI  AppRotateFiles
& $nssm get AgenticTraderAPI  AppRotateOnline
& $nssm get AgenticTraderAPI  AppRotateSeconds
& $nssm get AgenticTraderAPI  AppRotateBytes
& $nssm get AgenticTraderAPI  AppRotateBytesHigh
