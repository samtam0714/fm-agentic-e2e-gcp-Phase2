Step 5: Determine the asset type
Instructions:
asset_type: Identify the type of asset the alarm belongs to. Use one of the following asset types from the csv below, or if none are applicable then leave the field with null:
"Asset Type","Acronyms/Names","Asset Description"
"AC","AC","Air Conditioner"
"AHU","AHU|AH|FAHU|OAHU|PAHU|PAU|RAHU|VAHU","Air Handling Unit"
"Air Curtain","Air Curtain","An overdoor air curtain unit"
"Boiler","Boiler|BLR|BOI",""
CAV,CAV,Constant Air Volume
CEF,CEF,Ceiling Exhaust Fan
"Chilled Beam","Chilled Beam","Radiant Chilled Beam"
Chilled Water Plant,"Chilled Water Plant|Central Plant|Chilled Water System|CHWS|Cooling Plant|South Plant","Chilled Water Plant"
Chiller,"Chiller|CH",Chiller
CHWC,"Chilled Water Coil|CHWC",Chilled Water Coil
CHWP,CHWP,Chilled Water Pump
Computer Room,Computer Room,Computer Room,equip
CWP,CWP,Condenser Water Pump
Cooling Tower,"Cooling Tower|CT",Cooling Tower
Cooling Coil,"Cooling Coil|CC",Cooling Coil
CRAC,CRAC,Computer Room AC
CRAH,CRAH,Computer Room Air Handler
CUH,"CUH|UH",Cabinet Unit Heater,equip,,
CWM,CWM,Chilled Water Meter
DAHU,DAHU,Dedicated Outside Air Handling Unit
DDVAV,DDVAV,Dual Duct VAV
DH,DH,Duct Heater
DHW,DHW,Domestic Hot Water
DX,DX,Direct Expansion
EAF,"EAF|EF",Exhaust Air Fan
Electric Meter,"Electric Meter|Meter|Power Monitor",Electric Meter
ERV,"ERV|RERV",Energy Recovery Ventilator
FAF,FAF,Fresh Air Fan
FCU,"FCU|SFCU",Fan Coil Unit
FPB,"FPB|FPT|FPTU",Fan Powered Box
Generator,Generator,Generator,equip
Heat Pump,"Heat Pump|HP",Heat Pump
Heating Coil,"Heating Coil|HC",Heating Coil
HHWS,"HHWS|HWS|Hot Water Plant|Boiler Plant",Heating Hot Water System
Hot Water Coil,Hot Water Coil,Hot Water Coil
HWP,HWP,Hot Water Pump
HX,HX,Heat Exchanger
Lighting,Lighting,"An equipment to house general building lighting"
LCP,LCP,Lighting Control Panel
MADD,MADD,Mixed Air Dual Duct AHU
MASD,MASD,Mixed Air Single Duct AHU
MAU,"MAU|MUA",Makeup Air Unit
Multistack,"Multistack|MSTK",Multistack Modular Chillers
MZAHU,MZAHU,Multi Zone AHU
PTAC,PTAC,Packaged Terminal Air Conditioner
RM,RM,Room,equip
RTU,RTU,Packaged Rooftoop Unit
SAF,SAF,Supply Air Fan
VAV,VAV,Variable Air Volume
VFD,VFD,Variable Frequency Drive
Water Meter,Water Meter,Water Meter
 
Create and Consume Assets 
For each unique asset name predicted by the llm for a site, create a new asset in the db and publish the message for consumption by the navigation service. 
 
Note: While we won’t have built in mapping and could create duplicates, it helps us in the long run to track the assets predicted by the llm as records in our navigation service.
 
Alarm Insights - Data Entities
By JG
5 min
19
Add a reaction
We determined to start with Alarm Insights because we have lots of ingested alarms into production to work with. Issues and Email Events should be the primary entities we are interested in analyzing for this initiative.
As of 2024-11-13 we have this data ingested into production:
13 clients
688 sites
14,000+ Issues
300,000+ emails parsed into Issues
700,000+ emails unparsed into Issues
The two main entities that are worth analyzing for this initiative are Issues and Email Events. Below is a breakdown by client.
Client
Sites
Issues
Email Events
ASML
2
1,856
12569
BT
3
12
200
bbc Offices
1
130
1500
Cleveland Clinic
2
57
473
Davita
24
2,635
17,200
DLF
1
284
6623
Fifth Third Bank
609
2,583
14,500
FPL
2
91
1665
JTC
1
2
80
MS
32
5,641
163955
Motorola
2
460
70500
Scalpel
1
545
5822
Syngenta
8
118
1784
Data Entities
Issue
These are the aggregated events from various systems such as the alarm service. 
Field
Description
Issue Name
Unique name of Issue that tries to include the asset and issue type
Site
Association to the site within Facility Management
Assigned To
Facility Management User the Issue is assigned to (can be blank/null)
Floor
Floor Issues pertains too, generally always N/A today
Status
Defined list of statuses to track and organize Issues.
New, Dispatched, Dispatched Closed, Deferred, Complete, Auto Closed, Reviewed, and Review Complete
Timeline
Audit History of status changes
Resolution Code
Resolution to the Issue. Filled in once status is set to Complete.
Linked Workorders
List of attached workorders to the Issue
Type
Email: Any email sent to Facility Management, primarily from a Building Automation System alarm
Spark: Comes from SkySpark analytics application
Priority
P1, P2, P3, P4
Duration
Time between first and last event
Events
List of events attached to the Issue
Earliest Event
First event attached to the Issue
Latest Event
Most recent event attached to the Issue
Last Updated
Last datetime the Issue was updated
Alarm Event
Alarms are the events from emails that are processed and stored before being aggregated into an issue
Field
Description
Timestamp
The unix timestamp of the event
Name
The name of the event
Priority
The priority of the event
Project Name
Alias for client 
Site Name
The site or building where the alarm occurred
Subject
The email subject
Description
The text event description derived from the email body
Source
A unique identifier for the event from the source system
TZ
The timezone
State
The state of the system (Alarm / Normal) 
Value
A value (as text) provided by the sensor (temperate, humidity, etc)
 
Mailgun Email
These are emails that we receive from client systems in their raw format  
Field
Description
To
To email address. Individual email addresses are setup in Facility Management on a per client basis (i.e. ms@mail.fm-agentops.bbc.com)
From
From email address. Could be anything the sender sets up from the building automation system and is generally meaningless.
Sent Time
Datetime the email was sent from the source system
Subject
Email subject string
Raw Body
Email body string in plain text
HTML Body
Email body string in HTML format
In addition to all of the emails that have been parsed into Issues today, we have just over 1,000,000 emails in our production database.
 