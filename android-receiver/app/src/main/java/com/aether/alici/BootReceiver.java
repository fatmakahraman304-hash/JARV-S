package com.aether.alici;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** The projector was switched on (or the app updated): start listening again. */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context ctx, Intent intent) {
        ReceiverService.start(ctx);
    }
}
