# backend/models/lstm_model.py
import torch
import torch.nn as nn

class AttentionLSTMAnomaly(nn.Module):
    def __init__(self, feat_dim=1280, hidden=256):
        super().__init__()
        self.lstm = nn.LSTM(
            feat_dim, hidden,
            batch_first=True,
            bidirectional=True
        )
        self.attention = nn.Sequential(
            nn.Linear(hidden * 2, 128),
            nn.Tanh(),
            nn.Linear(128, 1)
        )
        self.classifier = nn.Linear(hidden * 2, 1)
        self.dropout = nn.Dropout(0.4)
    
    def forward(self, x, lengths):
        from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence
        
        packed = pack_padded_sequence(
            x, lengths.cpu(),
            batch_first=True,
            enforce_sorted=False
        )
        packed_out, (h, _) = self.lstm(packed)
        lstm_out, _ = pad_packed_sequence(packed_out, batch_first=True)
        
        attn_weights = self.attention(lstm_out).squeeze(2)
        attn_weights = torch.softmax(attn_weights, dim=1).unsqueeze(2)
        
        attended = (lstm_out * attn_weights).sum(dim=1)
        attended = self.dropout(attended)
        
        return self.classifier(attended).squeeze(1), attn_weights