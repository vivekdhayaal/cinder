# Copyright 2015 Reliance Jio Infocomm Ltd.

resource_action_mapping = {
"backups" : {
"/v2/{tenant_id}/backups"                           : { "POST" : "backup-create" },
"/v2/{tenant_id}/backups/{backup_id}/export_record" : { "GET" : "backup-export" },
"/v2/{tenant_id}/backups/import_record"             : { "POST" : "backup-import" },
"/v2/{tenant_id}/backups/detail"                    : { "GET" : "backup-list" },
"/v2/{tenant_id}/backups/{backup_id}/restore"       : { "POST" : "backup-restore" },
"/v2/{tenant_id}/backups/{backup_id}"               : {
"GET" : "backup-show",
"DELETE" : "backup-delete"
}
}, 

"volumes" : {
"/v2/{tenant_id}/volumes"                       :  { "POST" : "create" },
"/v2/{tenant_id}/volumes/{volume_id}/action"    :  { "POST" : {
"os-force_delete" : "force-delete",
"os-set_bootable" : "set-bootable",
}
},
"/v2/{tenant_id}/volumes/detail"                :  { "GET" : "list" },
"/v2/{tenant_id}/volumes/{volume_id}"           :  {
"GET" : "show",
"DELETE" : "delete"
}
},
	
"os-quota-class-sets" : {
"/v2/{tenant_id}/os-quota-class-sets/{tenant_id}" : {
"GET" : "quota-class-show",
"PUT" : "quota-class-update"
}
},

"os-quota-sets" : {
"/v2/{tenant_id}/os-quota-sets/{tenant_id}"            : { "PUT" : "quota-update" },
},

"limits" : {
"/v2/{tenant_id}/limits" : { "GET" : "limits" }
}
}

resource_id_mapping = { 
"backups" : "{backup_id}",
"volumes" : "{volume_id}",
"os-quota-class-sets" : "{tenant_id}",
"os-quota-sets" : "{tenant_id}"
}

TENANT_VARIABLE = "{tenant_id}"
